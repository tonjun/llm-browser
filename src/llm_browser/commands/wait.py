"""Wait command."""

from __future__ import annotations

import typer

from llm_browser.browser import wait as wait_


def register(app: typer.Typer) -> None:
    @app.command()
    def wait(
        selector: str = typer.Argument(
            None, help="Wait for this element (CSS selector or @eN ref)."
        ),
        ms: int = typer.Option(
            None, "--ms", help="Wait this many milliseconds instead."
        ),
        text: str = typer.Option(
            None, "--text", help="Wait for this text to appear on the page."
        ),
        url: str = typer.Option(
            None, "--url", help="Wait for the current URL to match this glob pattern."
        ),
        fn: str = typer.Option(
            None, "--fn", help="Wait for this JS expression to become truthy."
        ),
        timeout: float = typer.Option(25.0, "--timeout", help="Timeout in seconds."),
    ) -> None:
        """Wait for an element, text, URL, timeout, or JS condition."""
        if (
            selector is None
            and ms is None
            and text is None
            and url is None
            and fn is None
        ):
            raise typer.BadParameter(
                "wait needs a selector or one of --ms/--text/--url/--fn."
            )
        wait_.wait_for(
            selector=selector, ms=ms, text=text, url=url, js_fn=fn, timeout=timeout
        )
