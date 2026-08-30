"""Screenshots & PDF commands."""

from __future__ import annotations

import typer

from llm_browser.browser import capture


def register(app: typer.Typer) -> None:
    @app.command()
    def screenshot(
        path: str = typer.Argument(
            None, help="Output path (default: a generated path)."
        ),
        full: bool = typer.Option(
            False,
            "-f",
            "--full",
            help="Capture the full scrollable page, not just the viewport.",
        ),
    ) -> None:
        """Take a screenshot."""
        print(capture.screenshot(path, full_page=full))

    @app.command()
    def pdf(path: str = typer.Argument(..., help="Output path.")) -> None:
        """Save the current page as a PDF."""
        print(capture.save_pdf(path))
