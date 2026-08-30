"""Misc quick wins commands."""

from __future__ import annotations

import typer

from llm_browser.browser import gui, misc
from llm_browser.commands import _print


def register(app: typer.Typer) -> None:
    @app.command()
    def highlight(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Highlight an element."""
        misc.highlight(selector)

    @app.command()
    def read(
        selector: str = typer.Argument(None, help="Only this subtree (CSS selector)."),
    ) -> None:
        """Read the current page as plain text."""
        print(misc.read_page(selector))

    @app.command(name="internalize-links")
    def internalize_links() -> None:
        """Rewrite target="_blank" links to open in the same tab."""
        misc.internalize_links()

    @app.command(name="tile-windows")
    def tile_windows() -> None:
        """Tile open browser windows."""
        misc.tile_windows()

    @app.command(name="mfa-code")
    def mfa_code_cmd(
        totp_key: str = typer.Argument(
            None, help="TOTP secret key (or configured default)."
        ),
    ) -> None:
        """Generate a TOTP code for 2FA."""
        _print(misc.mfa_code(totp_key))

    @app.command(name="enter-mfa")
    def enter_mfa(
        selector: str = typer.Argument(
            ..., help="CSS selector or @eN ref for the code field."
        ),
        totp_key: str = typer.Argument(
            None, help="TOTP secret key (or configured default)."
        ),
    ) -> None:
        """Generate and enter a TOTP code into a field."""
        misc.enter_mfa(selector, totp_key)

    @app.command(name="gui-hover-click")
    def gui_hover_click(
        hover_selector: str = typer.Argument(..., help="Element to hover over first."),
        click_selector: str = typer.Argument(
            ..., help="Element to click after hovering."
        ),
    ) -> None:
        """Hover then click via the real OS pointer (PyAutoGUI); needs --headed."""
        gui.gui_hover_and_click(hover_selector, click_selector)
