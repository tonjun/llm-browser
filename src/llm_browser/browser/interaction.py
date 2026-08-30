"""Interaction: click, type, drag, scroll, and related element actions."""

from __future__ import annotations

import json as json_module
import time

import mycdp.input_ as cdp_input
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import (
    _is_checked_safe,
    _js_str,
    resolve_selector,
    with_driver,
)

# name -> (key, code, windowsVirtualKeyCode, text-to-insert-or-None).
# CDPMethods.press_keys()/type()/send_keys() all end up typing their
# argument as literal characters (see seleniumbase's Element.send_keys),
# so there is no way to ask them for a *named* key like "Enter" - passing
# "Enter" that way just types the five letters E-n-t-e-r. Named keys and
# modifier combos ("Control+a") need real CDP Input.dispatchKeyEvent
# calls instead, which is what _KEY_TABLE/_dispatch_key_combo below build.
_KEY_TABLE: dict[str, tuple[str, str, int, str | None]] = {
    "enter": ("Enter", "Enter", 13, "\r"),
    "return": ("Enter", "Enter", 13, "\r"),
    "tab": ("Tab", "Tab", 9, "\t"),
    "escape": ("Escape", "Escape", 27, None),
    "esc": ("Escape", "Escape", 27, None),
    "backspace": ("Backspace", "Backspace", 8, None),
    "delete": ("Delete", "Delete", 46, None),
    "del": ("Delete", "Delete", 46, None),
    "space": (" ", "Space", 32, " "),
    "home": ("Home", "Home", 36, None),
    "end": ("End", "End", 35, None),
    "pageup": ("PageUp", "PageUp", 33, None),
    "pagedown": ("PageDown", "PageDown", 34, None),
    "arrowup": ("ArrowUp", "ArrowUp", 38, None),
    "up": ("ArrowUp", "ArrowUp", 38, None),
    "arrowdown": ("ArrowDown", "ArrowDown", 40, None),
    "down": ("ArrowDown", "ArrowDown", 40, None),
    "arrowleft": ("ArrowLeft", "ArrowLeft", 37, None),
    "left": ("ArrowLeft", "ArrowLeft", 37, None),
    "arrowright": ("ArrowRight", "ArrowRight", 39, None),
    "right": ("ArrowRight", "ArrowRight", 39, None),
}
for _i in range(1, 13):
    _KEY_TABLE[f"f{_i}"] = (f"F{_i}", f"F{_i}", 111 + _i, None)

# modifier name -> (bit, key, code, windowsVirtualKeyCode), for combos
# like "Control+a".
_MODIFIER_TABLE: dict[str, tuple[int, str, str, int]] = {
    "alt": (1, "Alt", "AltLeft", 18),
    "option": (1, "Alt", "AltLeft", 18),
    "control": (2, "Control", "ControlLeft", 17),
    "ctrl": (2, "Control", "ControlLeft", 17),
    "meta": (4, "Meta", "MetaLeft", 91),
    "command": (4, "Meta", "MetaLeft", 91),
    "cmd": (4, "Meta", "MetaLeft", 91),
    "shift": (8, "Shift", "ShiftLeft", 16),
}


def _lookup_key(name: str) -> tuple[str, str | None, int | None, str | None]:
    entry = _KEY_TABLE.get(name.lower())
    if entry:
        return entry
    if len(name) == 1:
        if name.isalpha():
            return (name, f"Key{name.upper()}", ord(name.upper()), name)
        if name.isdigit():
            return (name, f"Digit{name}", ord(name), name)
        return (name, None, None, name)  # punctuation: text-only, no code
    raise ValueError(f"Unknown key: {name!r}")


def _dispatch_key_combo(d: CDPMethods, key_spec: str) -> None:
    parts = [p for p in key_spec.split("+") if p]
    if not parts:
        raise ValueError("press requires a key.")
    *mod_names, main = parts
    mods = []
    for name in mod_names:
        entry = _MODIFIER_TABLE.get(name.lower())
        if not entry:
            raise ValueError(f"Unknown modifier: {name!r}")
        mods.append(entry)
    key, code, vk, text = _lookup_key(main)
    non_shift_mods = any(bit != 8 for bit, *_ in mods)
    insert_text = text if not non_shift_mods else None

    async def _run() -> None:
        held = 0

        def _key_event(type_: str, k: str, c: str | None, v: int | None, txt=None):
            return cdp_input.dispatch_key_event(
                type_=type_,
                modifiers=held,
                key=k,
                code=c,
                windows_virtual_key_code=v,
                text=txt,
            )

        for bit, mkey, mcode, mvk in mods:
            held |= bit
            await d.page.send(_key_event("rawKeyDown", mkey, mcode, mvk))
        if insert_text is not None:
            await d.page.send(_key_event("keyDown", key, code, vk, insert_text))
        else:
            await d.page.send(_key_event("rawKeyDown", key, code, vk))
        await d.page.send(_key_event("keyUp", key, code, vk))
        for bit, mkey, mcode, mvk in reversed(mods):
            held &= ~bit
            await d.page.send(_key_event("keyUp", mkey, mcode, mvk))

    d.loop.run_until_complete(_run())


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
        "(() => {{ const el = document.querySelector({}); "
        "if (!el) throw new Error('Element not found: {}'); "
        "el.dispatchEvent(new MouseEvent('dblclick', "
        "{{bubbles: true, cancelable: true, view: window}})); }})()"
    ).format(_js_str(sel), sel.replace("'", "\\'"))
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
    def _run(d: CDPMethods) -> None:
        if selector:
            d.focus(resolve_selector(selector))
        _dispatch_key_combo(d, key)

    with_driver(_run)


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
        f"(() => {{ const el = document.querySelector({_js_str(sel)}); "
        f"const wanted = new Set({json_module.dumps(list(values))}); "
        "for (const opt of el.options) opt.selected = wanted.has(opt.value); "
        "el.dispatchEvent(new Event('change', {bubbles: true})); })()"
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


def scroll_until_count(
    selector: str, target: int, px: int = 2000, timeout: float = 25.0
) -> int:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> int:
        deadline = time.monotonic() + timeout
        last_count = -1
        while time.monotonic() < deadline:
            count = len(d.find_elements(sel))
            if count >= target or count == last_count:
                return count  # hit the target, or growth has stalled
            last_count = count
            d.scroll_down(px)
            d.sleep(0.5)
        return len(d.find_elements(sel))

    return with_driver(_run)


def scroll_into_view(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.scroll_into_view(sel))


def scroll_to_top() -> None:
    with_driver(lambda d: d.scroll_to_top())


def scroll_to_bottom() -> None:
    with_driver(lambda d: d.scroll_to_bottom())
