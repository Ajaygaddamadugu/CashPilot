"""Find clipped text in the running dashboard, in a real browser, at several desktop widths.

    cashpilot dashboard --headless --port 8501        # in one terminal
    python scripts/check_layout.py http://localhost:8501 [--widths 1280,1366,1536,1920]

A value is "clipped" when its text is wider than its box and the box hides the overflow (an ellipsis such as `40,265,...`).
It also reports a navigation bar that has to scroll and a page that scrolls sideways. Data tables are drawn on a canvas, so
their cells cannot be measured this way; Streamlit sizes those columns to their content. Exit code 1 when anything is found.
Uses Microsoft Edge or Google Chrome through the DevTools protocol (see take_screenshots.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from take_screenshots import BROWSERS, TABS, Cdp, wait_rendered                      # noqa: E402
from websockets.sync.client import connect                                          # noqa: E402

PORT = 9344
DEFAULT_WIDTHS = (1280, 1366, 1440, 1536, 1600, 1920)

# Boxes that cut their text off with an ellipsis and whose text is wider than the box, the tab bar and the page itself.
MEASURE = r"""
(() => {
  const found = [];
  for (const root of document.querySelectorAll('[data-testid="stSidebar"], [data-testid="stMain"]')) {
    for (const el of root.querySelectorAll('*')) {
      if (!el.clientWidth || el.scrollWidth <= el.clientWidth + 1 || !el.textContent.trim()) continue;
      if (getComputedStyle(el).textOverflow !== 'ellipsis') continue;
      const holder = el.closest('[data-testid]:not([data-testid="stMarkdownContainer"])');
      found.push({kind: 'text', where: holder ? holder.getAttribute('data-testid') : el.tagName, text: el.textContent.trim().slice(0, 48),
                  needs: el.scrollWidth, has: el.clientWidth});
    }
  }
  const tabs = document.querySelector('[role="tablist"]');
  if (tabs && tabs.scrollWidth > tabs.clientWidth + 1) found.push({kind: 'navigation', where: 'tab bar', text: 'the tabs need scrolling', needs: tabs.scrollWidth, has: tabs.clientWidth});
  const page = document.documentElement;
  if (page.scrollWidth > window.innerWidth + 1) found.push({kind: 'page', where: 'page', text: 'the page scrolls sideways', needs: page.scrollWidth, has: window.innerWidth});
  return JSON.stringify(found);
})()
"""


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("no Edge/Chrome found")


def measure(base: str, widths=DEFAULT_WIDTHS, browser: str | None = None, tabs=TABS) -> list[dict]:
    """Every clipped item, as {tab, width, kind, where, text, needs, has}."""
    profile = tempfile.mkdtemp(prefix="cashpilot-layout-")
    proc = subprocess.Popen([browser or find_browser(), "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results: list[dict] = []
    try:
        for _ in range(60):
            try:
                page = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        with connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            cdp = Cdp(ws)
            cdp.call("Page.enable")
            for name, tab, section in tabs:
                extra = f"&section={quote(section)}" if section else ""
                cdp.call("Emulation.setDeviceMetricsOverride", width=widths[-1], height=1000, deviceScaleFactor=1, mobile=False)
                cdp.call("Page.navigate", url=f"{base}/?tab={quote(tab)}{extra}")
                time.sleep(2)
                wait_rendered(cdp)
                for width in widths:
                    cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=1000, deviceScaleFactor=1, mobile=False)
                    time.sleep(0.8)                                  # let the layout settle after the resize
                    results += [{"tab": name, "width": width, **item} for item in json.loads(cdp.js(MEASURE) or "[]")]
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", nargs="?", default="http://localhost:8501")
    ap.add_argument("--widths", default=",".join(map(str, DEFAULT_WIDTHS)), help="browser widths in CSS pixels")
    ap.add_argument("--browser", help="path to Edge or Chrome")
    args = ap.parse_args()
    found = measure(args.base, tuple(int(w) for w in args.widths.split(",")), args.browser)
    seen = set()
    for f in found:
        key = (f["tab"], f["width"], f["kind"], f["where"], f["text"])
        if key not in seen:
            seen.add(key)
            print(f"{f['tab']:<26} {f['width']:>5}px  {f['kind']:<10} {f['where']:<22} needs {f['needs']}px, has {f['has']}px  | {f['text']}")
    print(f"\n{len(seen)} clipped item(s) at widths {args.widths}")
    return 1 if seen else 0


if __name__ == "__main__":
    raise SystemExit(main())
