"""Screenshots & PDF commands."""

from __future__ import annotations

import enum

import typer

from llm_browser.browser import capture


class ImageFormat(str, enum.Enum):
    png = "png"
    jpeg = "jpeg"
    webp = "webp"


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
        format: ImageFormat = typer.Option(
            ImageFormat.png,
            "--format",
            help="Image format: png (lossless, default), jpeg, or webp.",
        ),
        quality: int = typer.Option(
            None,
            "--quality",
            min=1,
            max=100,
            help=(
                "Compression quality 1-100 for jpeg/webp, to reduce file "
                "size. Not valid with --format png."
            ),
        ),
    ) -> None:
        """Take a screenshot."""
        if to_stdout and path:
            raise typer.BadParameter("path is not used with --stdout")
        if quality is not None and format == ImageFormat.png:
            raise typer.BadParameter("--quality requires --format jpeg or webp")
        print(
            capture.screenshot(
                path,
                full_page=full,
                to_stdout=to_stdout,
                format_=format.value,
                quality=quality,
            )
        )

    @app.command()
    def pdf(path: str = typer.Argument(..., help="Output path.")) -> None:
        """Save the current page as a PDF."""
        print(capture.save_pdf(path))
