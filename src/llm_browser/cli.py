"""Typer CLI entrypoint for llm-browser."""

import typer

from llm_browser import browser

app = typer.Typer(help="llm-browser: browser automation via SeleniumBase CDP Mode.")


@app.command()
def open(
    url: str = typer.Argument(..., help="URL to open."),
    headless: bool = typer.Option(False, "--headless", help="Run the browser headlessly."),
) -> None:
    """Open URL in a SeleniumBase CDP Mode browser session."""
    browser.open_url(url, headless=headless)


if __name__ == "__main__":
    app()
