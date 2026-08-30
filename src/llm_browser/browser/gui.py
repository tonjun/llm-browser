"""GUI-level fallback interactions (real OS pointer via PyAutoGUI).

Only meaningful against a real display: --headed (or, on Linux, the
daemon's auto-started Xvfb). There's no reliable way to detect
"headless" from here, so this is a documented caveat, not a guard.
"""

from __future__ import annotations

from llm_browser.browser.core import resolve_selector, with_driver


def gui_click(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.gui_click_element(sel))


def gui_hover_and_click(hover_selector: str, click_selector: str) -> None:
    h, c = resolve_selector(hover_selector), resolve_selector(click_selector)
    with_driver(lambda d: d.gui_hover_and_click(h, c))


def gui_drag(src: str, dst: str) -> None:
    s, t = resolve_selector(src), resolve_selector(dst)
    with_driver(lambda d: d.gui_drag_and_drop(s, t))
