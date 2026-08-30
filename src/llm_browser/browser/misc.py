"""Misc quick wins: highlight, online check, read-as-text, and small utilities."""

from __future__ import annotations

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import resolve_selector, with_driver


def highlight(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.highlight(sel))


def is_online() -> bool:
    return with_driver(lambda d: d.is_online())


def read_page(selector: str | None = None) -> str:
    def _run(d: CDPMethods) -> str:
        soup = d.get_beautiful_soup()
        if selector:
            node = soup.select_one(selector)
            return node.get_text(" ", strip=True) if node else ""
        return soup.get_text(" ", strip=True)

    return with_driver(_run)


def internalize_links() -> None:
    with_driver(lambda d: d.internalize_links())


def tile_windows() -> None:
    with_driver(lambda d: d.tile_windows())


def mfa_code(totp_key: str | None = None) -> str:
    return with_driver(lambda d: d.get_mfa_code(totp_key))


def enter_mfa(selector: str, totp_key: str | None = None) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.enter_mfa_code(sel, totp_key))
