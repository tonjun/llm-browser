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


def open_url(url: str, headless: bool = False) -> None:
    """Open a URL in the persistent browser session, starting it if needed."""
    existing = session.is_daemon_alive(session.read_state())
    state = _ensure_daemon(headless=headless)
    if existing and headless:
        print("Note: --headless is ignored; a session is already running.")

    _ensure_target(state)
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
# Attach helper: every command in the topic modules is a stateless "attach
# to the daemon's shared Chrome, call one or more sb_cdp methods, return" -
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
    _ensure_target(state)
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
