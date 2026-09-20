"""Post command: structured data for a social-media/forum post."""

from __future__ import annotations

import typer

from llm_browser.browser import post as post_mod


def register(app: typer.Typer) -> None:
    @app.command()
    def post(
        max_comments: int = typer.Option(
            200,
            "--max-comments",
            min=1,
            help="Maximum number of comments to include (document order).",
        ),
        no_comments: bool = typer.Option(
            False, "--no-comments", help="Omit the comments."
        ),
    ) -> None:
        """Print the open page's post as JSON: author, date, title, content,
        media, and nested comments (Reddit, X, HN, Facebook, Instagram, or
        any generic forum/blog page)."""
        print(
            post_mod.extract_post(
                max_comments=max_comments, include_comments=not no_comments
            )
        )
