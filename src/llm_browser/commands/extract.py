"""Extract command: readability-style main content from the open page."""

from __future__ import annotations

import typer

from llm_browser.browser import extract as extract_mod


def register(app: typer.Typer) -> None:
    @app.command()
    def extract(
        text: bool = typer.Option(
            False, "--text", help="Plain text instead of Markdown."
        ),
    ) -> None:
        """Extract the current page's main content (readability-style)."""
        print(extract_mod.extract_content(markdown=not text))

    @app.command("save-markdown")
    def save_markdown(
        path: str = typer.Argument(
            None, help="Output path (default: a generated path)."
        ),
    ) -> None:
        """Save the current page's main content as Markdown to disk."""
        print(extract_mod.save_markdown(path))
