"""SeleniumBase CDP Mode helpers.

Browser sessions are persistent: the first ``open`` call spawns a
detached background daemon that owns a Chrome instance, and every
subsequent call reconnects to that same instance over CDP instead of
launching a new browser. See :mod:`llm_browser.daemon` and
:mod:`llm_browser.session` for how that's coordinated, and
``docs/persistent-sessions.md`` for the full design.

Everything below ``open_url``/``close_session`` is a stateless
attach-call-return against the daemon's shared Chrome (see
``with_driver`` and ``_attach``), modeled on agent-browser's CLI
surface (see ``docs/commands.md`` for the user-facing reference and
``docs/snapshot-and-refs.md`` for the ``@ref`` system specifically).
"""

from __future__ import annotations

import asyncio
import fnmatch
import json as json_module
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

import mycdp
import mycdp.accessibility  # noqa: F401 - not re-exported by mycdp/__init__.py
from seleniumbase import sb_cdp
from seleniumbase.core.sb_cdp import CDPMethods
from seleniumbase.undetected.cdp_driver import cdp_util

from llm_browser import session

T = TypeVar("T")

_SPAWN_TIMEOUT = 10.0
_SPAWN_POLL_INTERVAL = 0.1

_REF_ATTR = "data-llmb-ref"
_REF_RE = re.compile(r"^@(e\d+)$")


def _spawn_daemon(headless: bool) -> None:
    args = [sys.executable, "-m", "llm_browser.daemon"]
    if headless:
        args.append("--headless")
    with open(session.log_file(), "ab") as log:
        subprocess.Popen(
            args,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def _wait_for_daemon() -> session.SessionState:
    deadline = time.monotonic() + _SPAWN_TIMEOUT
    while time.monotonic() < deadline:
        state = session.read_state()
        if session.is_daemon_alive(state):
            return state
        time.sleep(_SPAWN_POLL_INTERVAL)
    raise RuntimeError(
        "Timed out waiting for the llm-browser session daemon to start. "
        f"Check {session.log_file()} for details."
    )


def _kill_daemon_group(pid: int, sig: signal.Signals) -> None:
    """Signal the daemon's whole process group, not just its own pid.

    The daemon is spawned with ``start_new_session=True``, making it
    its own process group leader (pgid == pid), and Chrome is spawned
    as its plain child without its own detach. So a crashed daemon
    (e.g. killed with SIGKILL, which bypasses its SIGTERM handler)
    can leave an orphaned Chrome behind that a plain ``os.kill(pid,
    ...)`` on the recorded pid would miss - it still holds the
    profile's SingletonLock, so `killpg` here to reach the whole
    group is what makes crash recovery actually work.
    """
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _ensure_daemon(headless: bool) -> session.SessionState:
    """Return an alive session, spawning the daemon if none is running."""
    state = session.read_state()
    if session.is_daemon_alive(state):
        return state

    with session.spawn_lock() as acquired:
        if acquired:
            if state is not None:
                # A stale state usually means the daemon crashed or was
                # killed uncleanly; make sure nothing (e.g. an orphaned
                # Chrome still holding the profile lock) is left behind
                # before starting a fresh one in the same profile dir.
                _kill_daemon_group(state.pid, signal.SIGKILL)
            session.clear_state()
            _spawn_daemon(headless=headless)
        # Whether we spawned it or lost the race to another CLI
        # invocation doing the same thing, wait for it to come up.
        return _wait_for_daemon()


def open_url(url: str, headless: bool = False) -> None:
    """Open a URL in the persistent browser session, starting it if needed."""
    existing = session.is_daemon_alive(session.read_state())
    state = _ensure_daemon(headless=headless)
    if existing and headless:
        print("Note: --headless is ignored; a session is already running.")

    driver = sb_cdp.Chrome(host=state.host, port=state.port)
    driver.get(url)
    driver.sleep(2)
    print(driver.get_title())
    # Deliberately no driver.quit() here: this process only attached to
    # the daemon's Chrome instance (connect_existing), so quitting would
    # just close our CDP connection - it can't and shouldn't kill the
    # shared browser. Closing the session is done via `llm-browser close`.


def close_session() -> bool:
    """Shut down the persistent browser session, if one is running.

    Returns True if a running session was found and asked to stop.
    """
    state = session.read_state()
    if not session.is_daemon_alive(state):
        session.clear_state()
        return False

    os.kill(state.pid, signal.SIGTERM)

    deadline = time.monotonic() + _SPAWN_TIMEOUT
    while time.monotonic() < deadline:
        if session.read_state() is None:
            break
        time.sleep(_SPAWN_POLL_INTERVAL)
    else:
        # Daemon didn't shut down cleanly in time (e.g. driver.quit()
        # hung); force-kill its whole process group so Chrome doesn't
        # linger, then clear the stale state ourselves.
        _kill_daemon_group(state.pid, signal.SIGKILL)
        session.clear_state()

    return True


# --------------------------------------------------------------------------
# Attach helper: every command below this point is a stateless "attach to
# the daemon's shared Chrome, call one or more sb_cdp methods, return"  -
# never a driver.quit(), for the same reason as open_url() above.
# --------------------------------------------------------------------------


def _attach() -> CDPMethods:
    """Attach to the daemon's shared Chrome without disturbing its page.

    ``sb_cdp.Chrome(host=..., port=...)`` (used by ``open_url``) always
    navigates the most recently opened tab to ``about:blank`` on
    construction if no explicit URL is given (it defaults the ``url``
    kwarg and unconditionally calls ``Browser.get()``, which issues
    ``Page.navigate`` regardless of the URL). That's fine for
    ``open_url``, which immediately navigates again to the real target,
    but every other command here just wants to *read or act on the
    current page* - so this connects the same way (`cdp_util.start_sync`
    with ``host``/``port`` reconnects to the daemon's existing Chrome
    without launching a new one) and builds the same ``CDPMethods`` base
    class `sb_cdp.Chrome` wraps, minus the constructor's forced navigate.
    """
    state = session.read_state()
    if not session.is_daemon_alive(state):
        raise RuntimeError("No running session. Run `llm-browser open <url>` first.")
    loop = asyncio.new_event_loop()
    driver = cdp_util.start_sync(host=state.host, port=state.port, loop=loop)
    page = driver.tabs[-1]
    # Tab.closed just checks "is the websocket missing/closed", and the
    # websocket is only lazily opened on first send() - so a freshly
    # attached tab reads as "closed" until something sends on it. A few
    # sb_cdp methods (e.g. get_all_cookies) inspect `.closed` on *all*
    # tabs to pick a connection and skip ones that look closed, so open
    # it eagerly here rather than let those silently fall back to the
    # wrong (browser-level) connection.
    loop.run_until_complete(page.aopen())
    return CDPMethods(loop, page, driver)


def with_driver(fn: Callable[[CDPMethods], T]) -> T:
    return fn(_attach())


def resolve_selector(sel: str) -> str:
    """Resolve a plain CSS selector, or an ``@eN`` ref from ``snapshot``.

    Refs are resolved to ``[data-llmb-ref="eN"]`` - see the "Snapshot &
    @ref system" section of the implementation plan and
    ``docs/snapshot-and-refs.md`` for how refs get tagged onto elements.
    """
    m = _REF_RE.match(sel)
    return f'[{_REF_ATTR}="{m.group(1)}"]' if m else sel


def _js_str(value: str) -> str:
    """Safely embed a Python string as a JS string literal."""
    return json_module.dumps(value)


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------


def go_back() -> None:
    with_driver(lambda d: d.go_back())


def go_forward() -> None:
    with_driver(lambda d: d.go_forward())


def reload_page(ignore_cache: bool = False) -> None:
    with_driver(lambda d: d.reload(ignore_cache=ignore_cache))


# --------------------------------------------------------------------------
# Interaction
# --------------------------------------------------------------------------


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
        # Not d.check_if_unchecked(): it calls SeleniumBase's own raw
        # is_checked(), which raises KeyError (instead of returning
        # False) for the common case of an unchecked box with no literal
        # `checked` attribute at all - our is_checked() above already
        # works around that.
        try:
            checked = d.is_checked(sel)
        except KeyError:
            checked = False
        if not checked:
            d.click(sel)

    with_driver(_run)


def uncheck(selector: str) -> None:
    sel = resolve_selector(selector)

    def _run(d: CDPMethods) -> None:
        try:
            checked = d.is_checked(sel)
        except KeyError:
            checked = False
        if checked:
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


# --------------------------------------------------------------------------
# Wait
# --------------------------------------------------------------------------


def wait_for(
    selector: str | None = None,
    ms: int | None = None,
    text: str | None = None,
    url: str | None = None,
    js_fn: str | None = None,
    timeout: float = 25.0,
) -> None:
    def _run(d: CDPMethods) -> None:
        if ms is not None:
            d.sleep(ms / 1000)
            return
        if selector is not None:
            d.wait_for_element(resolve_selector(selector), timeout=timeout)
            return
        if text is not None:
            d.wait_for_text(text, selector="body", timeout=timeout)
            return
        if url is not None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if fnmatch.fnmatch(d.get_current_url(), url):
                    return
                d.sleep(0.2)
            raise TimeoutError(f"Timed out waiting for URL to match {url!r}")
        if js_fn is not None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if d.evaluate(js_fn):
                    return
                d.sleep(0.2)
            raise TimeoutError(f"Timed out waiting for condition: {js_fn!r}")
        raise ValueError("wait requires one of: selector, ms, text, url, js_fn")

    with_driver(_run)


# --------------------------------------------------------------------------
# Get info
# --------------------------------------------------------------------------


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
            "(() => { const s = getComputedStyle(document.querySelector(%s)); "
            "const o = {}; for (const k of s) o[k] = s.getPropertyValue(k); "
            "return JSON.stringify(o); })()" % _js_str(sel)
        )
    return with_driver(lambda d: d.evaluate(js))


def get_cdp_url() -> str:
    return with_driver(lambda d: d.get_websocket_url())


# --------------------------------------------------------------------------
# Check state
# --------------------------------------------------------------------------


def is_visible(selector: str) -> bool:
    return with_driver(lambda d: d.is_element_visible(resolve_selector(selector)))


def is_checked(selector: str) -> bool:
    # SeleniumBase's is_checked() raises KeyError instead of returning
    # False when the `checked` attribute is simply absent from the DOM
    # (the normal state of an unchecked checkbox), rather than reading
    # the live boolean property - work around that here.
    def _run(d: CDPMethods) -> bool:
        try:
            return d.is_checked(resolve_selector(selector))
        except KeyError:
            return False

    return with_driver(_run)


def is_enabled(selector: str) -> bool:
    # No native is_enabled(); absence of the `disabled` attribute is the
    # same check, done Python-side without an eval round trip.
    return with_driver(
        lambda d: d.get_attribute(resolve_selector(selector), "disabled") is None
    )


# --------------------------------------------------------------------------
# Screenshots & PDF
# --------------------------------------------------------------------------


def screenshot(path: str | None = None) -> str:
    def _run(d: CDPMethods) -> str:
        target = path or str(session.state_dir() / f"screenshot-{int(time.time() * 1000)}.png")
        folder = os.path.dirname(target) or "."
        name = os.path.basename(target)
        d.save_screenshot(name, folder=folder)
        return target

    return with_driver(_run)


def save_pdf(path: str) -> str:
    def _run(d: CDPMethods) -> str:
        folder = os.path.dirname(path) or "."
        name = os.path.basename(path)
        d.print_to_pdf(name, folder=folder)
        return path

    return with_driver(_run)


# --------------------------------------------------------------------------
# Eval
# --------------------------------------------------------------------------


def evaluate(js: str) -> Any:
    return with_driver(lambda d: d.evaluate(js))


# --------------------------------------------------------------------------
# Cookies & storage
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Tabs & windows
# --------------------------------------------------------------------------


def tab_new(url: str | None = None) -> None:
    with_driver(lambda d: d.open_new_tab(url))


def tab_list() -> list[dict]:
    def _run(d: CDPMethods) -> list[dict]:
        tabs = d.get_tabs()
        result = []
        for i, t in enumerate(tabs):
            target = getattr(t, "target", None)
            result.append(
                {
                    "index": i,
                    "url": getattr(target, "url", None),
                    "title": getattr(target, "title", None),
                }
            )
        return result

    return with_driver(_run)


def tab_switch(index: int) -> None:
    # SeleniumBase only accepts an int index (or a raw Tab object) here -
    # there's no persistent `t1`/`t2`/label system like agent-browser's;
    # use the index from `tab list`.
    with_driver(lambda d: d.switch_to_tab(index))


def tab_close(index: int | None = None) -> None:
    def _run(d: CDPMethods) -> None:
        if index is not None:
            d.switch_to_tab(index)
        d.close_active_tab()

    with_driver(_run)


def window_new(url: str | None = None) -> None:
    with_driver(lambda d: d.open_new_window(url))


# --------------------------------------------------------------------------
# Misc quick wins
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# GUI-level fallback interactions (real OS pointer via PyAutoGUI)
#
# Only meaningful against a real display: --headed (or, on Linux, the
# daemon's auto-started Xvfb). There's no reliable way to detect
# "headless" from here, so this is a documented caveat, not a guard.
# --------------------------------------------------------------------------


def gui_click(selector: str) -> None:
    sel = resolve_selector(selector)
    with_driver(lambda d: d.gui_click_element(sel))


def gui_hover_and_click(hover_selector: str, click_selector: str) -> None:
    h, c = resolve_selector(hover_selector), resolve_selector(click_selector)
    with_driver(lambda d: d.gui_hover_and_click(h, c))


def gui_drag(src: str, dst: str) -> None:
    s, t = resolve_selector(src), resolve_selector(dst)
    with_driver(lambda d: d.gui_drag_and_drop(s, t))


# --------------------------------------------------------------------------
# Captcha solving
#
# Auto-detects and clicks past whichever of five vendors SeleniumBase
# recognizes on the current page: Cloudflare Turnstile, Google
# reCAPTCHA v2 checkbox, hCaptcha (incl. Incapsula-hosted), a DataDome
# slider, and Friendly Captcha. Best-effort and markup-shape-dependent
# (SeleniumBase pattern-matches each vendor's known DOM structure), and
# only clears the checkbox/slider/token step - not challenges requiring
# actual content solving (e.g. image grids). Returns False (not an
# error) when no supported captcha is detected on the page.
# --------------------------------------------------------------------------


def solve_captcha(gui: bool = False) -> Any:
    # --gui drives the real OS pointer via PyAutoGUI instead of
    # CDP-dispatched events - needed for captcha types (e.g. the
    # DataDome slider) that check for genuine OS-level input, and
    # requires a real display for the same reason as the other gui_*
    # helpers above.
    return with_driver(lambda d: d.gui_click_captcha() if gui else d.solve_captcha())


# --------------------------------------------------------------------------
# Snapshot & @ref system
#
# Fetches the accessibility tree via raw CDP (Accessibility domain, not
# wrapped by sb_cdp - see docs/snapshot-and-refs.md for how this was
# verified against the installed seleniumbase package), then tags each
# included element in the live DOM with a `data-llmb-ref="eN"`
# attribute. Every other selector-taking command in this module then
# resolves `@eN` to `[data-llmb-ref="eN"]` via resolve_selector() and
# flows through the normal sb_cdp methods unchanged.
# --------------------------------------------------------------------------

_INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "option",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "slider",
    "spinbutton",
    "switch",
    "tab",
}

_SKIP_WHEN_COMPACT = {"generic", "none", "InlineTextBox"}
_NON_ELEMENT_ROLES = {
    "StaticText",
    "InlineTextBox",
    "LineBreak",
    # RootWebArea's backendDOMNodeId is the #document node, not <html> -
    # DOM.setAttributeValue on a document node throws a CDP protocol
    # error, which the underlying connection.send() swallows by closing
    # the websocket outright (see docs/snapshot-and-refs.md).
    "RootWebArea",
}


@dataclass
class _SnapshotNode:
    ax_id: str
    role: str
    name: str
    backend_dom_node_id: Any
    ignored: bool = False
    child_ids: list[str] = field(default_factory=list)
    ref: str | None = None


def _cdp_send(driver: CDPMethods, command: Any) -> Any:
    return driver.loop.run_until_complete(driver.page.send(command))


def _ax_value_str(value: Any) -> str:
    if value is None or value.value is None:
        return ""
    return str(value.value)


def _build_index(nodes: list) -> dict[str, _SnapshotNode]:
    # Keep ignored nodes in the index (just marked `ignored`) rather than
    # dropping them outright: a node CDP marks ignored can still be the
    # parent of perfectly meaningful children (e.g. a wrapper <div> with
    # no role, containing the actual heading/paragraph/link nodes), and
    # dropping it here would sever the tree above those children. Ignored
    # nodes are always excluded from the *rendered* output in
    # `_filter_and_level` instead, which also re-attaches their children
    # to the nearest kept ancestor.
    index: dict[str, _SnapshotNode] = {}
    for n in nodes:
        index[str(n.node_id)] = _SnapshotNode(
            ax_id=str(n.node_id),
            role=_ax_value_str(n.role) or "generic",
            name=_ax_value_str(n.name),
            backend_dom_node_id=n.backend_dom_node_id,
            ignored=n.ignored,
            child_ids=[str(c) for c in (n.child_ids or [])],
        )
    return index


def _find_root(index: dict[str, _SnapshotNode]) -> str | None:
    child_ids = {cid for node in index.values() for cid in node.child_ids}
    for ax_id in index:
        if ax_id not in child_ids:
            return ax_id
    return next(iter(index), None)


def _find_ax_id_for_selector(
    driver: CDPMethods, index: dict[str, _SnapshotNode], selector: str
) -> str:
    doc = _cdp_send(driver, mycdp.dom.get_document())
    node_id = _cdp_send(driver, mycdp.dom.query_selector(doc.node_id, selector))
    if not node_id:
        raise ValueError(f"No element matches selector: {selector!r}")
    described = _cdp_send(driver, mycdp.dom.describe_node(node_id=node_id))
    target_backend_id = int(described.backend_node_id)
    for ax_id, node in index.items():
        if node.backend_dom_node_id is not None and int(node.backend_dom_node_id) == target_backend_id:
            return ax_id
    raise ValueError(f"No accessibility node found for selector: {selector!r}")


def _iter_nodes(index: dict[str, _SnapshotNode], ax_id: str | None, raw_depth: int, depth_limit: int | None):
    """DFS over the raw AX tree, yielding (raw_depth, node) pairs."""
    if ax_id is None or ax_id not in index:
        return
    if depth_limit is not None and raw_depth > depth_limit:
        return
    node = index[ax_id]
    yield raw_depth, node
    for child_id in node.child_ids:
        yield from _iter_nodes(index, child_id, raw_depth + 1, depth_limit)


def _filter_and_level(pairs, interactive: bool, compact: bool):
    """Apply -i/-c filters, re-leveling so dropped nodes' children
    attach to the nearest kept ancestor (no gaps in the indentation)."""
    kept = []
    # Stack of (raw_depth, assigned_level) for the current ancestor chain.
    stack: list[tuple[int, int]] = []
    for raw_depth, node in pairs:
        while stack and stack[-1][0] >= raw_depth:
            stack.pop()
        parent_level = stack[-1][1] if stack else -1
        include = not node.ignored
        if interactive and node.role not in _INTERACTIVE_ROLES:
            include = False
        if compact and not node.name and node.role in _SKIP_WHEN_COMPACT:
            include = False
        if include:
            level = parent_level + 1
            kept.append((level, node))
            stack.append((raw_depth, level))
        else:
            stack.append((raw_depth, parent_level))
    return kept


def _render(levels, hrefs: dict, as_json: bool) -> str:
    items = []
    for level, node in levels:
        items.append(
            {
                "ref": f"@{node.ref}" if node.ref else None,
                "role": node.role,
                "name": node.name,
                "level": level,
                "href": hrefs.get(node.ref) if node.ref else None,
            }
        )
    if as_json:
        return json_module.dumps(items, indent=2)
    lines = []
    for item in items:
        indent = "  " * item["level"]
        ref_part = f'{item["ref"]} ' if item["ref"] else ""
        name_part = f' "{item["name"]}"' if item["name"] else ""
        href_part = f' href="{item["href"]}"' if item["href"] else ""
        lines.append(f'{indent}{ref_part}[{item["role"]}]{name_part}{href_part}')
    return "\n".join(lines)


def snapshot(
    interactive: bool = False,
    compact: bool = False,
    depth: int | None = None,
    selector: str | None = None,
    with_urls: bool = False,
    as_json: bool = False,
) -> str:
    def _run(d: CDPMethods) -> str:
        # Clear stale refs from a previous snapshot before assigning new
        # ones - refs are only ever meaningful for the snapshot that
        # produced them (see docs/snapshot-and-refs.md).
        d.evaluate(
            f"document.querySelectorAll('[{_REF_ATTR}]')"
            f".forEach(el => el.removeAttribute('{_REF_ATTR}'))"
        )
        _cdp_send(d, mycdp.accessibility.enable())
        _cdp_send(d, mycdp.dom.enable())
        # DOM.getDocument() must be called at least once to initialize
        # CDP's DOM node tracking - without it, backend node ids from the
        # accessibility tree can't be resolved (pushNodesByBackendIdsToFrontend
        # silently comes back empty/None otherwise).
        _cdp_send(d, mycdp.dom.get_document())
        nodes = _cdp_send(d, mycdp.accessibility.get_full_ax_tree())
        index = _build_index(nodes)
        if not index:
            return "[]" if as_json else ""

        root_id = _find_ax_id_for_selector(d, index, selector) if selector else _find_root(index)
        pairs = _iter_nodes(index, root_id, 0, depth)
        levels = _filter_and_level(pairs, interactive, compact)

        ref_n = 0
        for _, node in levels:
            # Text-node AX roles (Chrome's "StaticText"/"InlineTextBox"/
            # "LineBreak" internal roles) back onto DOM Text nodes, not
            # Elements - CDP can't set an attribute on those, and
            # pushNodesByBackendIdsToFrontend itself comes back empty for
            # them. Only Element-backed nodes are taggable/actionable.
            if node.backend_dom_node_id is None or node.role in _NON_ELEMENT_ROLES:
                continue
            ref_n += 1
            node.ref = f"e{ref_n}"
            node_ids = _cdp_send(
                d,
                mycdp.dom.push_nodes_by_backend_ids_to_frontend(
                    backend_node_ids=[node.backend_dom_node_id]
                ),
            )
            if not node_ids:
                # Shouldn't happen for an Element node, but don't let one
                # unexpected miss blow up the whole snapshot.
                node.ref = None
                ref_n -= 1
                continue
            _cdp_send(
                d,
                mycdp.dom.set_attribute_value(node_id=node_ids[0], name=_REF_ATTR, value=node.ref),
            )

        hrefs: dict = {}
        if with_urls:
            raw = d.evaluate(
                f"JSON.stringify([...document.querySelectorAll('[{_REF_ATTR}]')]"
                f".reduce((o, el) => (o[el.getAttribute('{_REF_ATTR}')] = el.href || null, o), {{}}))"
            )
            hrefs = json_module.loads(raw) if raw else {}

        return _render(levels, hrefs, as_json)

    return with_driver(_run)
