"""State-file helpers for the persistent browser daemon.

The daemon and the CLI processes coordinate through a small state
directory under the user's home rather than any in-memory IPC, since
each ``llm-browser`` invocation is a separate short-lived process.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import socket
import threading
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows has no fcntl; the daemon model relies on flock.
    raise SystemExit(
        "error: llm-browser supports macOS and Linux only; Windows is not supported."
    ) from None

# Override the state directory (session files *and* the Chrome profile)
# to run several fully isolated sessions on one machine - e.g. one per
# agent, or a throwaway profile for a test - instead of every invocation
# sharing one Chrome, one active-tab pointer and one login state.
_HOME_ENV = "LLM_BROWSER_HOME"


def state_dir() -> Path:
    """Return the state directory, creating it if needed.

    ``$LLM_BROWSER_HOME`` if set, else ``~/.llm-browser``.
    """
    override = os.environ.get(_HOME_ENV)
    path = Path(override).expanduser() if override else Path.home() / ".llm-browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_dir() -> Path:
    """Return the persistent Chrome profile directory."""
    path = state_dir() / "profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshots_dir() -> Path:
    """Default home for `screenshot` output, so files don't pile up next
    to the session state files."""
    path = state_dir() / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pages_dir() -> Path:
    """Default home for `save-markdown` output."""
    path = state_dir() / "pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return state_dir() / "daemon.log"


def session_file() -> Path:
    return state_dir() / "session.json"


def lock_file() -> Path:
    return state_dir() / "session.lock"


def command_lock_file() -> Path:
    return state_dir() / "command.lock"


def labels_file() -> Path:
    return state_dir() / "labels.json"


def active_tab_file() -> Path:
    return state_dir() / "active_tab"


@dataclasses.dataclass
class SessionState:
    pid: int
    host: str
    port: int


def read_state() -> SessionState | None:
    """Read the current session state, or ``None`` if there isn't one."""
    try:
        data = json.loads(session_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    try:
        return SessionState(pid=data["pid"], host=data["host"], port=data["port"])
    except KeyError:
        return None


def write_state(pid: int, host: str, port: int) -> None:
    session_file().write_text(json.dumps({"pid": pid, "host": host, "port": port}))


def clear_state() -> None:
    with contextlib.suppress(FileNotFoundError):
        session_file().unlink()


def read_labels() -> dict[str, str]:
    """Return the tab label -> CDP targetId mapping, or ``{}`` if none.

    Kept in its own file rather than folded into ``session.json`` so that
    respawning the daemon (which rewrites ``session.json`` via
    ``write_state``) doesn't need to round-trip label data it has nothing
    to do with.
    """
    try:
        return json.loads(labels_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_labels(labels: dict[str, str]) -> None:
    labels_file().write_text(json.dumps(labels))


def clear_labels() -> None:
    with contextlib.suppress(FileNotFoundError):
        labels_file().unlink()


def read_active_tab() -> str | None:
    """Return the CDP targetId of the tab commands should attach to next.

    Every ``llm-browser`` invocation is a separate process that reattaches
    to the daemon's shared Chrome from scratch (see ``browser/core.py``'s
    ``_attach``), so without this, a `tab switch` in one invocation had no
    way to affect which tab the *next* invocation (e.g. `extract`) landed
    on - it just always picked the most-recently-opened tab. Stored as a
    plain string rather than JSON since it's a single scalar.
    """
    try:
        target_id = active_tab_file().read_text().strip()
    except FileNotFoundError:
        return None
    return target_id or None


def write_active_tab(target_id: str) -> None:
    active_tab_file().write_text(target_id)


def clear_active_tab() -> None:
    with contextlib.suppress(FileNotFoundError):
        active_tab_file().unlink()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else - treat as alive.
        return True
    return True


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_daemon_alive(state: SessionState | None) -> bool:
    """Check whether the daemon described by ``state`` is actually running.

    Both the pid and the debug port must respond; a half-dead state
    (e.g. after a crash) is treated as not running.
    """
    if state is None:
        return False
    if not _pid_alive(state.pid):
        return False
    return _port_open(state.host, state.port)


@contextlib.contextmanager
def spawn_lock():
    """Best-effort lock so concurrent CLI invocations don't both spawn a daemon.

    Non-blocking ``flock`` on a lock file. Yields True if the lock was
    acquired, False if another process currently holds it. Unlike an
    ``O_EXCL``-created marker file, an ``flock`` is released by the kernel
    when its holder exits for any reason - so a CLI process killed mid-spawn
    can't leave a stale lock behind that makes every later ``open`` wait
    out the spawn timeout and fail.
    """
    fd = os.open(lock_file(), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


_command_lock_local = threading.local()


@contextlib.contextmanager
def command_lock():
    """Blocking, cross-process lock serializing commands against the daemon.

    The daemon has exactly one "active tab" pointer (``active_tab_file``,
    read/written by ``browser/core.py`` and ``browser/tabs.py``), so two
    ``llm-browser`` invocations running at once can race on it - e.g. one
    opening a tab and marking it active just as another reads/overwrites
    that pointer, or one closing "the active tab" while a different
    process is still mid-extract on what it thought was its own tab (see
    the write-up in the commit that added this). Unlike ``spawn_lock``
    (best-effort, non-blocking, only for daemon startup), this blocks
    until acquired via ``flock`` so a second invocation queues instead of
    racing the first.

    Reentrant *within one process/thread* (tracked with a depth counter)
    so a caller that already holds it - e.g. ``tab_new_extract`` wrapping
    several separate ``with_driver`` calls (open, scroll, extract, close)
    in one lock so the whole sequence is atomic - doesn't deadlock on
    itself when those calls take the lock again internally.
    """
    depth = getattr(_command_lock_local, "depth", 0)
    if depth == 0:
        fd = os.open(command_lock_file(), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        _command_lock_local.fd = fd
    _command_lock_local.depth = depth + 1
    try:
        yield
    finally:
        _command_lock_local.depth -= 1
        if _command_lock_local.depth == 0:
            fcntl.flock(_command_lock_local.fd, fcntl.LOCK_UN)
            os.close(_command_lock_local.fd)
            del _command_lock_local.fd
