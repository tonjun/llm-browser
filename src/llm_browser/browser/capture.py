"""Screenshots & PDF."""

from __future__ import annotations

import os
import time

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser import session
from llm_browser.browser.core import with_driver


def screenshot(path: str | None = None) -> str:
    def _run(d: CDPMethods) -> str:
        target = path or str(session.state_dir() / f"screenshot-{int(time.time() * 1000)}.png")
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
