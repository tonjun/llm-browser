"""Captcha solving commands."""

from __future__ import annotations

import typer

from llm_browser.browser import captcha


def register(app: typer.Typer) -> None:
    @app.command(name="solve-captcha")
    @app.command(name="click-captcha")
    def solve_captcha(
        gui: bool = typer.Option(
            False, "--gui", help="Solve via real OS pointer (PyAutoGUI) instead of CDP; needs --headed."
        ),
    ) -> None:
        """Auto-detect and solve/click past a supported captcha on the page.

        Supports Cloudflare Turnstile, Google reCAPTCHA v2 checkbox,
        hCaptcha, DataDome sliders, and Friendly Captcha. Best-effort and
        markup-shape-dependent - see docs/commands.md for the full caveat.
        """
        result = captcha.solve_captcha(gui=gui)
        # `solve_captcha()`/`click_captcha()` return None regardless of
        # outcome (SeleniumBase discards the inner True/False); only
        # `gui_click_captcha()` reliably returns False for "nothing
        # detected". Treat both as "can't confirm a captcha was solved"
        # rather than claiming success either way.
        if result in (False, None):
            print("No supported captcha detected on this page (or nothing to confirm).")
            raise typer.Exit(code=1)
