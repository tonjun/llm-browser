"""Navigation commands: open, close, back, forward, reload."""

from __future__ import annotations

import typer

from llm_browser.browser import core, navigation


def register(app: typer.Typer) -> None:
    @app.command()
    def open(
        url: str = typer.Argument(..., help="URL to open."),
        headless: bool = typer.Option(False, "--headless", help="Run the browser headlessly."),
    ) -> None:
        """Open URL in a SeleniumBase CDP Mode browser session.

        The browser session is persistent: the first call starts a
        background browser and leaves it running; later calls reuse it.
        """
        core.open_url(url, headless=headless)

    @app.command()
    def close() -> None:
        """Close the persistent browser session, if one is running."""
        if core.close_session():
            print("Session closed.")
        else:
            print("No running session.")

    @app.command()
    def back() -> None:
        """Go back."""
        navigation.go_back()

    @app.command()
    def forward() -> None:
        """Go forward."""
        navigation.go_forward()

    @app.command()
    def reload(
        ignore_cache: bool = typer.Option(False, "--ignore-cache", help="Bypass the cache on reload."),
    ) -> None:
        """Reload the current page."""
        navigation.reload_page(ignore_cache=ignore_cache)
