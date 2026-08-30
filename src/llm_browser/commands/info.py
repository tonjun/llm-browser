"""Get info sub-app: text, html, value, attr, title, url, count, box, styles, cdp-url."""

from __future__ import annotations

import typer

from llm_browser.browser import info
from llm_browser.commands import _print


def register(get_app: typer.Typer) -> None:
    @get_app.command("text")
    def get_text(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Get an element's visible text."""
        _print(info.get_text(selector))

    @get_app.command("html")
    def get_html(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Get an element's innerHTML."""
        _print(info.get_html(selector))

    @get_app.command("value")
    def get_value(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Get an input's value."""
        _print(info.get_value(selector))

    @get_app.command("attr")
    def get_attr(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        name: str = typer.Argument(..., help="Attribute name."),
    ) -> None:
        """Get an element's attribute."""
        _print(info.get_attr(selector, name))

    @get_app.command("title")
    def get_title() -> None:
        """Get the page title."""
        _print(info.get_title())

    @get_app.command("url")
    def get_url() -> None:
        """Get the current URL."""
        _print(info.get_url())

    @get_app.command("count")
    def get_count(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
        """Count matching elements."""
        _print(info.get_count(selector))

    @get_app.command("box")
    def get_box(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Get an element's bounding box."""
        _print(info.get_box(selector))

    @get_app.command("styles")
    def get_styles(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        prop: str = typer.Option(
            None, "--prop", help="Only this computed style property."
        ),
    ) -> None:
        """Get an element's computed styles."""
        _print(info.get_styles(selector, prop=prop))

    @get_app.command("cdp-url")
    def get_cdp_url() -> None:
        """Get the CDP WebSocket URL."""
        _print(info.get_cdp_url())
