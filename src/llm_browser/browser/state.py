"""Check state: visible, checked, enabled."""

from __future__ import annotations

from llm_browser.browser.core import _is_checked_safe, resolve_selector, with_driver


def is_visible(selector: str) -> bool:
    return with_driver(lambda d: d.is_element_visible(resolve_selector(selector)))


def is_checked(selector: str) -> bool:
    return with_driver(lambda d: _is_checked_safe(d, resolve_selector(selector)))


def is_enabled(selector: str) -> bool:
    # No native is_enabled(); absence of the `disabled` attribute is the
    # same check, done Python-side without an eval round trip.
    return with_driver(
        lambda d: d.get_attribute(resolve_selector(selector), "disabled") is None
    )
