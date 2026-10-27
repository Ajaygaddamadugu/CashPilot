"""Capture screenshots of the running dashboard with headless Edge/Chrome (Chrome DevTools Protocol).

    cashpilot dashboard --headless --port 8501        # in one terminal
    python scripts/take_screenshots.py http://localhost:8501 docs/screenshots

A plain `--screenshot` only captures Streamlit's loading skeleton, because the page renders over a
websocket. This script waits until the script run has finished before capturing each tab. It needs
`websockets` (installed with the dashboard extra) and Microsoft Edge or Google Chrome.
"""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

from websockets.sync.client import connect

BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "google-chrome", "chromium", "microsoft-edge"]
TABS = {"01-cash-overview": "Cash overview", "02-accounts-currencies": "Accounts & currencies", "03-forecast": "Forecast",
        "04-cash-flow-drivers": "Cash-flow drivers", "05-exceptions": "Exceptions", "06-actual-vs-forecast": "Actual vs forecast",
        "07-audit-exports": "Audit & exports"}
PORT = 9333


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("no Edge/Chrome found")


class Cdp:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(self, expr: str):
        return self.call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")


def wait_rendered(cdp: Cdp, timeout: int = 120) -> None:
    """Rendered = tabs exist and Streamlit's 'running' indicator has been gone for two consecutive checks."""
    quiet, end = 0, time.time() + timeout
    while time.time() < end:
        ready = cdp.js("document.querySelectorAll('[data-testid=\"stTab\"]').length > 0")
        running = cdp.js("document.querySelector('[data-testid=\"stStatusWidget\"]') !== null")
        quiet = quiet + 1 if ready and not running else 0
        if quiet >= 2:
            time.sleep(2.5)          # let the charts finish drawing
            return
        time.sleep(1.5)
    raise TimeoutError("the dashboard did not finish rendering")


def main(base: str, out: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="cashpilot-shots-")
    proc = subprocess.Popen([find_browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
                             f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        with connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            capture_all(Cdp(ws), base, out_dir)
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)


def capture_all(cdp: Cdp, base: str, out_dir: Path) -> None:
    def viewport(height: int) -> None:
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=height, deviceScaleFactor=1, mobile=False)

    cdp.call("Page.enable")
    viewport(2400)
    for name, tab in TABS.items():
        cdp.call("Page.navigate", url=f"{base}/?tab={quote(tab)}")
        time.sleep(2)
        wait_rendered(cdp)
        height = int(cdp.js("Math.max(document.querySelector('[data-testid=\"stMain\"]')?.scrollHeight || 0, 900)"))
        viewport(min(height + 40, 4000))          # tall enough that the whole tab is visible
        time.sleep(1.5)
        data = cdp.call("Page.captureScreenshot", format="png")["data"]
        (out_dir / f"{name}.png").write_bytes(base64.b64decode(data))
        print(f"{name}.png  ({tab}, {height}px)")
        viewport(2400)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501", sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
