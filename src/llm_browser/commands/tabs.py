"""Tabs & windows sub-apps."""

from __future__ import annotations

import typer

from llm_browser.browser import tabs
from llm_browser.commands import _print, _reject_headless_and_headed


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
        snapshot: bool = typer.Option(
            False,
            "--snapshot",
            help=(
                "With --extract, get an accessibility-tree snapshot and render "
                "that as Markdown, instead of the default trafilatura extraction."
            ),
        ),
        close: bool = typer.Option(
            False,
            "--close",
            help="With --extract, close the tab again after extracting.",
        ),
        until_stable: bool = typer.Option(
            False,
            "--until-stable",
            help="With --extract, scroll down until page height stops growing "
            "before extracting (for virtualized/infinite-scroll pages like "
            "Reddit).",
        ),
        stable_rounds: int = typer.Option(
            None,
            "--stable-rounds",
            help="Consecutive non-growing checks required before considering "
            "the page stable (with --until-stable; default 2).",
        ),
        timeout: float = typer.Option(
            None,
            "--timeout",
            help="Max seconds to scroll for (with --until-stable; default 30).",
        ),
        label: str = typer.Option(
            None, "--label", help="Assign a label to the new tab."
        ),
        headless: bool = typer.Option(
            False,
            "--headless",
            help="Run headless if a new session needs to be started.",
        ),
        headed: bool = typer.Option(
            False,
            "--headed",
            help="Force a real visible browser window if a new session "
            "needs to be started (skips the Xvfb fallback on Linux).",
        ),
    ) -> None:
        """Open a new tab."""
        _reject_headless_and_headed(headless, headed)
        if extract:
            if not url:
                raise typer.BadParameter("URL is required when using --extract.")
            if label:
                raise typer.BadParameter("--label can't be combined with --extract.")
            if snapshot and text:
                raise typer.BadParameter("--snapshot can't be combined with --text.")
            print(
                tabs.tab_new_extract(
                    url,
                    markdown=not text,
                    close=close,
                    headless=headless,
                    headed=headed,
                    snapshot=snapshot,
                    until_stable=until_stable,
                    timeout=timeout if timeout is not None else 30.0,
                    stable_rounds=stable_rounds if stable_rounds is not None else 2,
                )
            )
        else:
            if until_stable or stable_rounds is not None or timeout is not None:
                raise typer.BadParameter(
                    "--until-stable/--stable-rounds/--timeout require --extract."
                )
            tabs.tab_new(url, label=label, headless=headless, headed=headed)

    @tab_app.command("list")
    def tab_list() -> None:
        """List open tabs."""
        _print(tabs.tab_list())

    @tab_app.command("switch")
    def tab_switch(
        ref: str = typer.Argument(
            ...,
            help="Tab index from `tab list` (or -1 for newest), or a label "
            "assigned with `tab new --label`.",
        ),
    ) -> None:
        """Switch to a tab by index or label."""
        tabs.tab_switch(ref)

    @tab_app.command("close")
    def tab_close(
        ref: str = typer.Argument(
            None, help="Tab index or label to close (default: current tab)."
        ),
    ) -> None:
        """Close a tab."""
        tabs.tab_close(ref)

    @window_app.command("new")
    def window_new(
        url: str = typer.Argument(None, help="URL to open in the new window."),
    ) -> None:
        """Open a new window."""
        tabs.window_new(url)
