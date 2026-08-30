"""Navigation commands: back, forward, reload."""

from __future__ import annotations

from llm_browser.browser.core import with_driver


def go_back() -> None:
    with_driver(lambda d: d.go_back())


def go_forward() -> None:
    with_driver(lambda d: d.go_forward())


def reload_page(ignore_cache: bool = False) -> None:
    with_driver(lambda d: d.reload(ignore_cache=ignore_cache))
