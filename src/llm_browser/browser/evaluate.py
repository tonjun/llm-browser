"""Eval: run arbitrary JavaScript in the page."""

from __future__ import annotations

from typing import Any

from llm_browser.browser.core import with_driver


def evaluate(js: str) -> Any:
    return with_driver(lambda d: d.evaluate(js))
