"""Capture the real Streamlit demo at desktop and mobile viewports."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request

from _common import ROOT, task_environment
from playwright.sync_api import sync_playwright

PORT = 8502
URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Streamlit stopped before its health endpoint became ready")
        try:
            with urllib.request.urlopen(f"{URL}/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("Streamlit health endpoint was not ready within 30 seconds")


def _server() -> subprocess.Popen[str]:
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "src/wattwraith/app.py",
            "--server.headless=true",
            f"--server.port={PORT}",
            "--browser.gatherUsageStats=false",
        ],
        cwd=ROOT,
        env=task_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )


def main() -> int:
    output_dir = ROOT / "docs" / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    process = _server()
    try:
        _wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(URL, wait_until="networkidle")
            page.get_by_role("button", name="Run real analysis").click()
            page.get_by_role("heading", name="Power timeline").wait_for()
            page.get_by_text("31.536 kWh", exact=True).wait_for()
            page.get_by_role(
                "heading",
                name="Game console (synthetic)",
            ).scroll_into_view_if_needed()
            page.screenshot(
                path=output_dir / "wattwraith-result.png",
                full_page=False,
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(
                path=output_dir / "wattwraith-mobile.png",
                full_page=False,
            )
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    print(f"Captured real UI screenshots in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
