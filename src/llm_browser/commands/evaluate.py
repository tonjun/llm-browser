"""Eval command."""

from __future__ import annotations

import sys

import typer

from llm_browser.browser import evaluate as evaluate_
from llm_browser.commands import _print


def register(app: typer.Typer) -> None:
    @app.command()
    def eval(
        js: str = typer.Argument(None, help="JavaScript to evaluate."),
        stdin: bool = typer.Option(
            False, "--stdin", help="Read the script from stdin instead."
        ),
    ) -> None:
        """Evaluate JavaScript in the page."""
        script = sys.stdin.read() if stdin else js
        if not script:
            raise typer.BadParameter("Provide a script argument or use --stdin.")
        _print(evaluate_.evaluate(script))
