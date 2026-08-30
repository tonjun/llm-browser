"""Interaction: click, type, drag, scroll, and related element actions."""

from __future__ import annotations

import json as json_module

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import _is_checked_safe, _js_str, resolve_selector, with_driver


def click(selector: str | None = None, text: str | None = None) -> None:
    if not text and not selector:
        raise ValueError("click requires a selector or --text.")

    def _run(d: CDPMethods) -> None:
        if text:
            d.find_element_by_text(text).click()
        else:
            d.click(resolve_selector(selector))

    with_driver(_run)


def dblclick(selector: str) -> None:
    sel = resolve_selector(selector)
    js = (
        "(() => { const el = document.querySelector(%s); "
        "if (!el) throw new Error('Element not found: %s'); "
        "el.dispatchEvent(new MouseEvent('dblclick', "
        "{bubbles: true, cancelable: true, view: window})); })()"
        % (_js_str(sel), sel.replace("'", "\\'"))
    )
    with_driver(lambda d: d.evaluate(js))


def type_text(selector: str, text: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.send_keys(sel, text))


def fill(selector: str, text: str) -> None:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> None:
        d.clear(sel)
        d.type(sel, text)

    with_driver(_run)


def press(key: str, selector: str | None = None) -> None:
    # No selector-less "send to whatever has focus" primitive is exposed
    # directly; ``:focus`` is a valid querySelector pseudo-class in
    # Chrome, so it stands in for "the currently focused element" when
    # no selector is given.
    sel = resolve_selector(selector) if selector else ":focus"
    with_driver(lambda d: d.press_keys(sel, key))


def hover(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.hover_element(sel))


def focus(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.focus(sel))


def check(selector: str) -> None:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> None:
        if not _is_checked_safe(d, sel):
            d.click(sel)

    with_driver(_run)


def uncheck(selector: str) -> None:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> None:
        if _is_checked_safe(d, sel):
            d.click(sel)

    with_driver(_run)


def select_option(selector: str, values: list[str]) -> None:
    sel = resolve_selector(selector)
    if len(values) == 1:
        with_driver(lambda d: d.select_option_by_value(sel, values[0]))
        return
    # No native multi-select helper - set .selected on each matching
    # <option> directly and fire one `change` event.
    js = (
        "(() => { const el = document.querySelector(%s); "
        "const wanted = new Set(%s); "
        "for (const opt of el.options) opt.selected = wanted.has(opt.value); "
        "el.dispatchEvent(new Event('change', {bubbles: true})); })()"
        % (_js_str(sel), json_module.dumps(list(values)))
    )
    with_driver(lambda d: d.evaluate(js))


def drag(src: str, dst: str) -> None:
    s, t = resolve_selector(src), resolve_selector(dst)
    with_driver(lambda d: d.drag_and_drop(s, t))


def upload(selector: str, files: list[str]) -> None:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> None:
        element = d.find_element(sel)
        element.send_file(*files)

    with_driver(_run)


def scroll(direction: str, px: int = 300) -> None:
    def _run(d: CDPMethods) -> None:
        if direction == "down":
            d.scroll_down(px)
        elif direction == "up":
            d.scroll_up(px)
        elif direction == "left":
            d.evaluate(f"window.scrollBy(-{px}, 0)")
        elif direction == "right":
            d.evaluate(f"window.scrollBy({px}, 0)")
        else:
            raise ValueError(f"Unknown scroll direction: {direction!r}")

    with_driver(_run)


def scroll_into_view(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.scroll_into_view(sel))


def scroll_to_top() -> None:
    with_driver(lambda d: d.scroll_to_top())


def scroll_to_bottom() -> None:
    with_driver(lambda d: d.scroll_to_bottom())
