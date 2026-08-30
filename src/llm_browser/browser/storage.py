"""Cookies & storage."""

from __future__ import annotations

import json as json_module
from typing import Any

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import _js_str, with_driver


def cookies_get() -> Any:
    def _run(d: CDPMethods) -> list[dict]:
        cookies = d.get_all_cookies() or []
        return [c.to_json() if hasattr(c, "to_json") else c for c in cookies]

    return with_driver(_run)


def cookies_set(name: str, value: str) -> None:
    # `set_all_cookies` proxies to SeleniumBase's own cookie-jar helper
    # with an undocumented kwargs shape; a direct `document.cookie`
    # write is the reliable path for the simple "one name/value" case.
    js = f"document.cookie = {_js_str(name)} + '=' + {_js_str(value)} + '; path=/'"
    with_driver(lambda d: d.evaluate(js))


def cookies_clear() -> None:
    with_driver(lambda d: d.clear_cookies())


def storage_get(key: str | None = None, use_session: bool = False) -> Any:
    def _run(d: CDPMethods) -> Any:
        if key is None:
            store = "sessionStorage" if use_session else "localStorage"
            raw = d.evaluate(f"JSON.stringify({store})")
            return json_module.loads(raw) if raw else {}
        if use_session:
            return d.get_session_storage_item(key)
        return d.get_local_storage_item(key)

    return with_driver(_run)


def storage_set(key: str, value: str, use_session: bool = False) -> None:
    def _run(d: CDPMethods) -> None:
        if use_session:
            d.set_session_storage_item(key, value)
        else:
            d.set_local_storage_item(key, value)

    with_driver(_run)


def storage_clear(use_session: bool = False) -> None:
    store = "sessionStorage" if use_session else "localStorage"
    with_driver(lambda d: d.evaluate(f"{store}.clear()"))
