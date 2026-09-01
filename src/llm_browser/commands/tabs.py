"""Tabs & windows sub-apps."""

from __future__ import annotations

import typer

from llm_browser.browser import tabs
from llm_browser.commands import _print


def register(tab_app: typer.Typer, window_app: typer.Typer) -> None:
    @tab_app.command("new")
    def tab_new(
        url: str = typer.Argument(None, help="URL to open in the new tab."),
        extract: bool = typer.Option(
            False,
            "--extract",
            help="Extract the page's main content as Markdown after opening.",
        ),
        text: bool = typer.Option(
            False, "--text", help="With --extract, plain text instead of Markdown."
        ),
        close: bool = typer.Option(
            False,
            "--close",
            help="With --extract, close the tab again after extracting.",
        ),
    ) -> None:
        """Open a new tab."""
        if extract:
            if not url:
                raise typer.BadParameter("URL is required when using --extract.")
            print(tabs.tab_new_extract(url, markdown=not text, close=close))
        else:
            tabs.tab_new(url)

    @tab_app.command("list")
    def tab_list() -> None:
        """List open tabs."""
        _print(tabs.tab_list())

    @tab_app.command("switch")
    def tab_switch(
        index: int = typer.Argument(
            ..., help="Tab index from `tab list` (or -1 for newest)."
        ),
    ) -> None:
        """Switch to a tab by index."""
        tabs.tab_switch(index)

    @tab_app.command("close")
    def tab_close(
        index: int = typer.Argument(
            None, help="Tab index to close (default: current tab)."
        ),
    ) -> None:
        """Close a tab."""
        tabs.tab_close(index)

    @window_app.command("new")
    def window_new(
        url: str = typer.Argument(None, help="URL to open in the new window."),
    ) -> None:
        """Open a new window."""
        tabs.window_new(url)
