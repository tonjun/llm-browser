"""Get info: text, html, value, attr, title, url, count, box, styles, cdp-url."""

from __future__ import annotations

from llm_browser.browser.core import _js_str, resolve_selector, with_driver


def get_text(selector: str) -> str:
    return with_driver(lambda d: d.get_text(resolve_selector(selector)))


def get_html(selector: str) -> str:
    return with_driver(lambda d: d.get_element_html(resolve_selector(selector)))


def get_value(selector: str) -> str | None:
    return with_driver(lambda d: d.get_attribute(resolve_selector(selector), "value"))


def get_attr(selector: str, name: str) -> str | None:
    return with_driver(lambda d: d.get_attribute(resolve_selector(selector), name))


def get_title() -> str:
    return with_driver(lambda d: d.get_title())


def get_url() -> str:
    return with_driver(lambda d: d.get_current_url())


def get_count(selector: str) -> int:
    # Done Python-side via find_elements rather than a JS eval, to avoid
    # escaping the selector string into a script.
    return with_driver(lambda d: len(d.find_elements(resolve_selector(selector))))


def get_box(selector: str) -> dict:
    return with_driver(lambda d: d.get_element_rect(resolve_selector(selector)))


def get_styles(selector: str, prop: str | None = None) -> str:
    sel = resolve_selector(selector)
    if prop:
        js = (
            f"getComputedStyle(document.querySelector({_js_str(sel)}))"
            f".getPropertyValue({_js_str(prop)})"
        )
    else:
        js = (
            f"(() => {{ const s = getComputedStyle(document.querySelector({_js_str(sel)})); "
            "const o = {}; for (const k of s) o[k] = s.getPropertyValue(k); "
            "return JSON.stringify(o); })()"
        )
    return with_driver(lambda d: d.evaluate(js))


def get_cdp_url() -> str:
    return with_driver(lambda d: d.get_websocket_url())
