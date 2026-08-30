"""Snapshot & refs command."""

from __future__ import annotations

import typer

from llm_browser.browser import snapshot as snapshot_


def register(app: typer.Typer) -> None:
    @app.command()
    def snapshot(
        interactive: bool = typer.Option(False, "-i", "--interactive", help="Only interactive elements."),
        compact: bool = typer.Option(False, "-c", "--compact", help="Remove empty structural nodes."),
        depth: int = typer.Option(None, "-d", "--depth", help="Limit tree depth."),
        selector: str = typer.Option(None, "-s", "--selector", help="Scope to a CSS selector."),
        with_urls: bool = typer.Option(False, "-u", "--urls", help="Include href URLs on links."),
        as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
    ) -> None:
        """Accessibility-tree snapshot with @eN refs for use with other commands.

        See docs/snapshot-and-refs.md for how refs work and their caveats
        (staleness on navigation, no cross-origin iframe inlining).
        """
        print(
            snapshot_.snapshot(
                interactive=interactive,
                compact=compact,
                depth=depth,
                selector=selector,
                with_urls=with_urls,
                as_json=as_json,
            )
        )
