"""Typer command wrappers, one module per :mod:`llm_browser.browser` topic.

Each module defines a ``register(app)`` function that attaches its
``@app.command()``s to the Typer app (or sub-app) it's given; ``cli.py``
owns building the Typer app(s) and calls every ``register()``.
"""

from __future__ import annotations

import json as json_module
from typing import Any


def _print(result: Any) -> None:
    if result is None:
        return
    if isinstance(result, str):
        print(result)
    else:
        print(json_module.dumps(result, indent=2, default=str))
