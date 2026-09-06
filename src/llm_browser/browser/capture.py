"""Screenshots & PDF."""

from __future__ import annotations

import os
import time

import mycdp.page
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser import session
from llm_browser.browser.core import with_driver


def screenshot(
    path: str | None = None, full_page: bool = False, to_stdout: bool = False
) -> str:
    def _run(d: CDPMethods) -> str:
        if to_stdout:
            # Same CDP call the file-writing paths below use under the
            # hood (Page.captureScreenshot, which already returns
            # base64-encoded PNG data) - called directly here so the
            # bytes never touch disk at all.
            data = d.loop.run_until_complete(
                d.page.send(
                    mycdp.page.capture_screenshot(
                        format_="png", capture_beyond_viewport=full_page
                    )
                )
            )
            if not data:
                raise RuntimeError(
                    "Could not take screenshot (page may not have finished "
                    "loading)."
                )
            return f"data:image/png;base64,{data}"

        target = path or str(
            session.state_dir() / f"screenshot-{int(time.time() * 1000)}.png"
        )
        if full_page:
            # CDPMethods.save_screenshot has no full_page option; drop to the
            # underlying async Tab.save_screenshot, which uses CDP's
            # Page.captureScreenshot(captureBeyondViewport=...) directly.
            d.loop.run_until_complete(d.page.save_screenshot(target, full_page=True))
        else:
            folder = os.path.dirname(target) or "."
            name = os.path.basename(target)
            d.save_screenshot(name, folder=folder)
        return target

    return with_driver(_run)


def save_pdf(path: str) -> str:
    def _run(d: CDPMethods) -> str:
        folder = os.path.dirname(path) or "."
        name = os.path.basename(path)
        d.print_to_pdf(name, folder=folder)
        return path

    return with_driver(_run)
