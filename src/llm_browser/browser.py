"""SeleniumBase CDP Mode helpers.

Browser sessions are persistent: the first ``open`` call spawns a
detached background daemon that owns a Chrome instance, and every
subsequent call reconnects to that same instance over CDP instead of
launching a new browser. See :mod:`llm_browser.daemon` and
:mod:`llm_browser.session` for how that's coordinated, and
``docs/persistent-sessions.md`` for the full design.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from seleniumbase import sb_cdp

from llm_browser import session

_SPAWN_TIMEOUT = 10.0
_SPAWN_POLL_INTERVAL = 0.1


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
