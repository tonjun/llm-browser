"""Typer CLI entrypoint for llm-browser."""

import typer

from llm_browser import browser

app = typer.Typer(help="llm-browser: browser automation via SeleniumBase CDP Mode.")


@app.command()
def open(
    url: str = typer.Argument(..., help="URL to open."),
    headless: bool = typer.Option(False, "--headless", help="Run the browser headlessly."),
) -> None:
    """Open URL in a SeleniumBase CDP Mode browser session.

    The browser session is persistent: the first call starts a
    background browser and leaves it running; later calls reuse it.
    """
    browser.open_url(url, headless=headless)


@app.command()
def close() -> None:
    """Close the persistent browser session, if one is running."""
    if browser.close_session():
        print("Session closed.")
    else:
        print("No running session.")


if __name__ == "__main__":
    app()
