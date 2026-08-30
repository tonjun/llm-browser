"""Captcha solving.

Auto-detects and clicks past whichever of five vendors SeleniumBase
recognizes on the current page: Cloudflare Turnstile, Google
reCAPTCHA v2 checkbox, hCaptcha (incl. Incapsula-hosted), a DataDome
slider, and Friendly Captcha. Best-effort and markup-shape-dependent
(SeleniumBase pattern-matches each vendor's known DOM structure), and
only clears the checkbox/slider/token step - not challenges requiring
actual content solving (e.g. image grids). Returns False (not an
error) when no supported captcha is detected on the page.
"""

from __future__ import annotations

from typing import Any

from llm_browser.browser.core import with_driver


def solve_captcha(gui: bool = False) -> Any:
    # --gui drives the real OS pointer via PyAutoGUI instead of
    # CDP-dispatched events - needed for captcha types (e.g. the
    # DataDome slider) that check for genuine OS-level input, and
    # requires a real display for the same reason as the other gui_*
    # helpers in browser/gui.py.
    return with_driver(lambda d: d.gui_click_captcha() if gui else d.solve_captcha())
