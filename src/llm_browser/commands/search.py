"""Search command: query a known search engine/site and return results."""

from __future__ import annotations

import typer

from llm_browser.browser import search as search_mod


def register(app: typer.Typer) -> None:
    @app.command()
    def search(
        engine: str = typer.Argument(
            ...,
            help="google, bing, duckduckgo (ddg), reddit, hn (hackernews), or github.",
        ),
        query: str = typer.Argument(..., help="Search query."),
    ) -> None:
        """Search a known engine/site and return the results snapshot."""
        print(search_mod.search(engine, query))
