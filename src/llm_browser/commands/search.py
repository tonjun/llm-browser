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
        as_json: bool = typer.Option(
            False,
            "--json",
            help="Print a JSON array of {title, url, snippet} instead of the "
            "snapshot (google, bing, duckduckgo, ddg only).",
        ),
        pages: int = typer.Option(
            1,
            "--pages",
            min=1,
            max=5,
            help="Number of result pages to fetch and merge into one array "
            "(requires --json; google and bing only).",
        ),
    ) -> None:
        """Search a known engine/site and return the results snapshot."""
        print(search_mod.search(engine, query, as_json=as_json, pages=pages))
