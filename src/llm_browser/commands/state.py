"""Check state sub-app: visible, enabled, checked, online."""

from __future__ import annotations

import typer

from llm_browser.browser import misc, state
from llm_browser.commands import _print


def register(is_app: typer.Typer) -> None:
    @is_app.command("visible")
    def is_visible(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Check whether an element is visible."""
        _print(state.is_visible(selector))

    @is_app.command("enabled")
    def is_enabled(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Check whether an element is enabled."""
        _print(state.is_enabled(selector))

    @is_app.command("checked")
    def is_checked(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Check whether a checkbox is checked."""
        _print(state.is_checked(selector))

    @is_app.command("online")
    def is_online() -> None:
        """Check whether the browser has network connectivity."""
        _print(misc.is_online())
