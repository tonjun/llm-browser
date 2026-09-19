"""Daemon lifecycle and the shared attach-call-return plumbing.

Every command module in :mod:`llm_browser.browser` builds on
``with_driver``/``_attach`` here to talk to the daemon's shared Chrome
instance - never a ``driver.quit()``, for the same reason as
``open_url`` below. See ``docs/persistent-sessions.md`` for the full
design.
"""

from __future__ import annotations

import asyncio
import json as json_module
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from typing import TypeVar

import requests
from seleniumbase.core.sb_cdp import CDPMethods
from seleniumbase.undetected.cdp_driver import cdp_util
from seleniumbase.undetected.cdp_driver.connection import Connection

from llm_browser import session

T = TypeVar("T")

# Cold Chrome starts (first run, slow disk) can take well over 10s; the
# poll interval keeps the common fast path just as quick.
_SPAWN_TIMEOUT = 30.0
_SPAWN_POLL_INTERVAL = 0.1

# How long a single CDP command may wait for its response before we give
# up on it. Plenty for real work (page loads etc. are handled by our own
# higher-level polling, not this), but short enough to fail loudly instead
# of hanging the process.
_CDP_COMMAND_TIMEOUT = 30.0

_cdp_send_patched = False

_REF_ATTR = "data-llmb-ref"
_REF_RE = re.compile(r"^@(e\d+)$")


def _patch_cdp_send_timeout() -> None:
    """Make ``Connection.send`` give up instead of hanging forever.

    Every CDP command is sent as a ``Transaction`` (an ``asyncio.Future``,
    see the vendored ``connection.py``) and awaited with no timeout of its
    own. If the tab it was sent to gets closed - by another
    ``llm-browser`` invocation racing this one (see
    ``session.command_lock``), or by the page/user closing it directly -
    the websocket just closes; ``Connection``'s listener loop reacts by
    logging and breaking out, but it never resolves or cancels whatever
    ``Transaction`` futures were still pending in ``self.mapper``. Nothing
    above that in the stack times out either, so the CLI process hangs
    indefinitely.

    ``command_lock`` closes the race that mainly triggers this, but this
    patch is the actual fix for the hang itself - a closed/dead tab should
    surface as an error, not wedge the process. Wraps the original
    coroutine in ``asyncio.wait_for``: on timeout that cancels it, which
    (since ``Transaction`` is itself the awaited ``Future``) throws
    ``CancelledError`` into the pending ``await tx`` - not caught by
    ``send``'s own ``except Exception`` (``CancelledError`` isn't an
    ``Exception`` subclass on the Python versions this project supports),
    so it propagates out and ``wait_for`` turns it into a ``TimeoutError``.
    Idempotent - safe to call more than once (e.g. under a test runner
    that imports this module repeatedly). ``Connection`` uses a metaclass
    that rejects plain ``Connection.send = ...`` (it exists to stop
    accidental class-level overrides that would leak across unrelated
    instances - exactly what a *deliberate* global patch like this one
    wants) - ``type.__setattr__`` goes around that hook.
    """
    global _cdp_send_patched
    if _cdp_send_patched:
        return
    _orig_send = Connection.send

    async def _send(self, cdp_obj, _is_update=True):
        try:
            return await asyncio.wait_for(
                _orig_send(self, cdp_obj, _is_update),
                timeout=_CDP_COMMAND_TIMEOUT,
            )
        except TimeoutError:
            raise TimeoutError(
                f"CDP command timed out after {_CDP_COMMAND_TIMEOUT:.0f}s "
                "(the tab it was sent to is likely closed or gone)."
            ) from None

    type.__setattr__(Connection, "send", _send)
    _cdp_send_patched = True


_patch_cdp_send_timeout()


def _spawn_daemon(headless: bool, headed: bool) -> None:
    args = [sys.executable, "-m", "llm_browser.daemon"]
    if headless:
        args.append("--headless")
    elif headed:
        args.append("--headed")
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


def _ensure_daemon(headless: bool, headed: bool) -> session.SessionState:
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
            _spawn_daemon(headless=headless, headed=headed)
        # Whether we spawned it or lost the race to another CLI
        # invocation doing the same thing, wait for it to come up.
        return _wait_for_daemon()


def _ensure_target(state: session.SessionState) -> None:
    """Make sure the daemon's Chrome has at least one open tab.

    A user closing every browser window manually leaves the daemon
    process and its CDP port alive (``is_daemon_alive`` only checks the
    pid and the port, not tab count), but with zero targets. Both
    ``sb_cdp.Chrome(...)`` (``open_url``) and ``cdp_util.start_sync``
    (``_attach``) pick "the" tab by indexing into that target list -
    ``main_tab``/``driver.tabs[-1]`` - so a Chrome with no tabs makes
    them crash with an ``IndexError`` instead of just opening a new one.
    Use the CDP HTTP endpoint to create a blank tab first when needed;
    it works even with zero existing targets.
    """
    base = f"http://{state.host}:{state.port}"
    targets = requests.get(f"{base}/json/list", timeout=5).json()
    if not any(t.get("type") == "page" for t in targets):
        requests.put(f"{base}/json/new", timeout=5)


def ensure_session(
    headless: bool = False, headed: bool = False
) -> session.SessionState:
    """Start the daemon if it's not already running, and return its state.

    Composes the same two steps ``open_url`` uses below: spawn (or reuse)
    the daemon, then make sure its Chrome has at least one open tab.
    """
    state = _ensure_daemon(headless=headless, headed=headed)
    _ensure_target(state)
    return state


def wait_for_load(d: CDPMethods, timeout: float = 15.0, settle: float = 0.25) -> None:
    """Block until ``document.readyState`` is ``complete`` (or ``timeout``).

    Used after navigations that don't wait for the page themselves (e.g.
    ``open_new_tab``, which returns as soon as the target exists) instead
    of a fixed multi-second sleep: returns as soon as the page is actually
    ready, and never hangs past ``timeout`` on a page that keeps loading.
    A short ``settle`` afterwards gives client-side rendering a beat.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if d.evaluate("document.readyState") == "complete":
            break
        time.sleep(0.1)
    if settle:
        time.sleep(settle)


def open_url(
    url: str, headless: bool = False, headed: bool = False, quiet: bool = False
) -> None:
    """Open a URL in the persistent browser session, starting it if needed.

    Prints the page title unless ``quiet`` (for callers whose stdout must
    stay machine-readable, e.g. ``search --json``).
    """
    existing = session.is_daemon_alive(session.read_state())
    _ensure_daemon(headless=headless, headed=headed)
    if existing and headless:
        print(
            "Note: --headless is ignored; a session is already running.",
            file=sys.stderr,
        )
    if existing and headed:
        print(
            "Note: --headed is ignored; a session is already running.",
            file=sys.stderr,
        )

    # Navigate via the same attach path every other command uses, rather
    # than `sb_cdp.Chrome(host=..., port=...)`: that constructor always
    # navigates the *newest* tab (ignoring the `tab switch` pointer) to
    # about:blank before we even get to the real URL, and it ran outside
    # the command lock. `_attach` honors the active tab, and `d.get()`
    # already waits for the load itself. No driver.quit() here either -
    # see the attach helper below.
    def _run(d: CDPMethods) -> None:
        d.get(url)
        wait_for_load(d, settle=0)
        if not quiet:
            print(d.get_title())

    with_driver(_run)


def close_session() -> bool:
    """Shut down the persistent browser session, if one is running.

    Returns True if a running session was found and asked to stop.
    """
    state = session.read_state()
    if not session.is_daemon_alive(state):
        if state is not None:
            # Stale state: the daemon died (or was SIGKILLed) but its Chrome
            # may still be running and holding the profile lock. Reap the
            # whole group now rather than leaving it for the next `open`.
            _kill_daemon_group(state.pid, signal.SIGKILL)
        session.clear_state()
        session.clear_labels()
        session.clear_active_tab()
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

    # A closed session means every tab (and its CDP targetId) is gone, so
    # any label or active-tab pointer would be meaningless in the next one.
    session.clear_labels()
    session.clear_active_tab()
    return True


# --------------------------------------------------------------------------
# Attach helper: every command in the topic modules is a stateless "attach
# to the daemon's shared Chrome, call one or more sb_cdp methods, return" -
# never a driver.quit(), for the same reason as open_url() above.
# --------------------------------------------------------------------------


def _active_page(driver):
    """Pick the tab an attach should operate on.

    Defaults to the most-recently-opened tab (``driver.tabs[-1]``), same
    as always, but honors a targetId previously recorded by ``tab switch``
    (see ``browser/tabs.py``) so that switching tabs in one CLI invocation
    actually carries over to the next one - without this, `tab switch`
    only affected the process that ran it, since every invocation reattaches
    from scratch and re-picks the newest tab.
    """
    target_id = session.read_active_tab()
    if target_id is not None:
        for tab in driver.tabs:
            if getattr(tab.target, "target_id", None) == target_id:
                return tab
        # The tab we were pointed at is gone (closed some other way) -
        # drop the stale pointer and fall through to the default below.
        session.clear_active_tab()
    return driver.tabs[-1]


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
    _ensure_target(state)
    loop = asyncio.new_event_loop()
    driver = cdp_util.start_sync(host=state.host, port=state.port, loop=loop)
    page = _active_page(driver)
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
    # Serialize against other CLI invocations touching the daemon's shared
    # Chrome - see session.command_lock() for why. Reentrant, so callers
    # that already hold it (tabs.py's tab_new_extract, wrapping several
    # with_driver calls in one) don't deadlock on themselves here.
    with session.command_lock():
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


def _is_checked_safe(d: CDPMethods, sel: str) -> bool:
    # Not d.check_if_unchecked(): it calls SeleniumBase's own raw
    # is_checked(), which raises KeyError (instead of returning False)
    # for the common case of an unchecked box with no literal `checked`
    # attribute at all - work around that here so callers get a plain
    # bool regardless.
    try:
        return d.is_checked(sel)
    except KeyError:
        return False
