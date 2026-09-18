"""Screenshots & PDF."""

from __future__ import annotations

import base64
import os
import pathlib
import time

import mycdp.page
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser import session
from llm_browser.browser.core import with_driver

_EXTENSIONS = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}


def screenshot(
    path: str | None = None,
    full_page: bool = False,
    to_stdout: bool = False,
    format_: str = "png",
    quality: int | None = None,
) -> str:
    def _run(d: CDPMethods) -> str:
        # Page.captureScreenshot already returns base64-encoded image data,
        # so every capture (stdout or file) goes through it directly rather
        # than SeleniumBase's save_screenshot helpers, none of which forward
        # a quality setting.
        data = d.loop.run_until_complete(
            d.page.send(
                mycdp.page.capture_screenshot(
                    format_=format_, quality=quality, capture_beyond_viewport=full_page
                )
            )
        )
        if not data:
            raise RuntimeError(
                "Could not take screenshot (page may not have finished loading)."
            )

        if to_stdout:
            return f"data:image/{format_};base64,{data}"

        target = path or str(
            session.screenshots_dir()
            / f"screenshot-{int(time.time() * 1000)}{_EXTENSIONS[format_]}"
        )
        pathlib.Path(target).write_bytes(base64.b64decode(data))
        return target

    return with_driver(_run)


def save_pdf(path: str) -> str:
    def _run(d: CDPMethods) -> str:
        folder = os.path.dirname(path) or "."
        name = os.path.basename(path)
        d.print_to_pdf(name, folder=folder)
        return path

    return with_driver(_run)
