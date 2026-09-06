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
        to_stdout: bool = typer.Option(
            False,
            "--stdout",
            help=(
                "Print a data:image/png;base64,... URI to stdout instead of "
                "writing a file."
            ),
        ),
    ) -> None:
        """Take a screenshot."""
        if to_stdout and path:
            raise typer.BadParameter("path is not used with --stdout")
        print(capture.screenshot(path, full_page=full, to_stdout=to_stdout))

    @app.command()
    def pdf(path: str = typer.Argument(..., help="Output path.")) -> None:
        """Save the current page as a PDF."""
        print(capture.save_pdf(path))
