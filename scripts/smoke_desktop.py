"""Start the frozen app and request real UI routes before wrapping the installer."""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

BINARIES = {
    "darwin": "DBVisual.app/Contents/MacOS/DBVisual",
    "win32": "DBVisual/DBVisual.exe",
    "linux": "DBVisual/DBVisual",
}


def check_layout(base_url: str, browser_name: str) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch()
        page = browser.new_page()
        for width, height in [(360, 640), (785, 548), (1366, 768)]:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(base_url + "/schema")
            expect(page.get_by_role("combobox")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            page.goto(base_url + "/connections")
            identity = page.get_by_label("Current identity", exact=False)
            identity.fill("draft@example.test")
            page.get_by_role("button", name="Help", exact=True).click()
            dialog = page.get_by_role("dialog")
            guide = dialog.frame_locator("iframe")
            heading = guide.get_by_role("heading", name="First steps", exact=True)
            expect(heading).to_have_css("font-size", "22px" if width <= 480 else "26px")
            if width <= 840:
                guide.get_by_text("Guide topics", exact=True).click()
            guide.get_by_role("link", name="Import a CSV file", exact=True).click()
            expect(guide.locator("#csv")).to_be_in_viewport()
            assert guide.locator(".hlp").evaluate(
                "e => [...e.querySelectorAll('a[href^=\"#\"]')].every("
                "a => document.getElementById(a.hash.slice(1)))"
            )
            guide.locator("#faq").scroll_into_view_if_needed()
            back = dialog.get_by_role("button", name="Back to app")
            expect(back).to_be_in_viewport()
            back.click()
            expect(identity).to_have_value("draft@example.test")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["chromium", "webkit"])
    args = parser.parse_args()
    executable = Path(__file__).resolve().parents[1] / "dist" / BINARIES[sys.platform]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, BROWSER="echo")
    with subprocess.Popen(
        [str(executable), "--mode", "web", "--port", str(port)], env=env
    ) as child:
        try:
            for route in ("/", "/connections", "/help"):
                deadline = time.monotonic() + 60
                while True:
                    if child.poll() is not None:
                        raise RuntimeError(
                            f"Frozen app exited with status {child.returncode}."
                        )
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{port}{route}", timeout=5
                        ) as response:
                            if b"nicegui" not in response.read().lower():
                                raise RuntimeError(f"Unexpected response for {route}")
                        break
                    except URLError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.25)
            if args.browser:
                check_layout(f"http://127.0.0.1:{port}", args.browser)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()


if __name__ == "__main__":
    main()
