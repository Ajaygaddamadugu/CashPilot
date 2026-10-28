"""No text is cut off in the real dashboard, in a real browser, at common desktop widths.

Opt-in because it needs Microsoft Edge or Google Chrome, the `websockets` package and about two minutes:

    CASHPILOT_LAYOUT_TEST=1 pytest tests/test_dashboard_layout.py

(The same check is available as `python scripts/check_layout.py URL` against a dashboard that is already running.)
"""

import importlib.util
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("websockets")
if not os.environ.get("CASHPILOT_LAYOUT_TEST"):
    pytest.skip("set CASHPILOT_LAYOUT_TEST=1 to run the browser layout check", allow_module_level=True)

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_layout", REPO / "scripts" / "check_layout.py")
check_layout = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(REPO / "scripts"))
spec.loader.exec_module(check_layout)


@pytest.fixture(scope="module")
def dashboard():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "cashpilot.cli", "dashboard", "--headless", "--port", str(port), "--data", "data/starter"],
                            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(90):
            try:
                if urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2).read() == b"ok":
                    break
            except Exception:
                time.sleep(1)
        else:
            pytest.fail("the dashboard did not start")
        yield f"http://localhost:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def test_no_figure_label_or_tab_name_is_cut_off_at_common_desktop_widths(dashboard):
    try:
        check_layout.find_browser()
    except SystemExit:
        pytest.skip("no Edge or Chrome found")
    found = check_layout.measure(dashboard, widths=(1280, 1366, 1440, 1536, 1920))
    report = sorted({(f["tab"], f["width"], f["kind"], f["text"], f["needs"], f["has"]) for f in found})
    assert not report, "\n".join(map(str, report))
