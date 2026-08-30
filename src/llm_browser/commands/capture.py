"""Screenshots & PDF commands."""

from __future__ import annotations

import typer

from llm_browser.browser import capture


def register(app: typer.Typer) -> None:
    @app.command()
    def screenshot(path: str = typer.Argument(None, help="Output path (default: a generated path).")) -> None:
        """Take a screenshot (viewport only - see docs/commands.md for the --full caveat)."""
        print(capture.screenshot(path))

    @app.command()
    def pdf(path: str = typer.Argument(..., help="Output path.")) -> None:
        """Save the current page as a PDF."""
        print(capture.save_pdf(path))
