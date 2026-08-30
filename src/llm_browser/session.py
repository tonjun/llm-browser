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
from pathlib import Path


def state_dir() -> Path:
    """Return ``~/.llm-browser``, creating it if needed."""
    path = Path.home() / ".llm-browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_dir() -> Path:
    """Return the persistent Chrome profile directory."""
    path = state_dir() / "profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return state_dir() / "daemon.log"


def session_file() -> Path:
    return state_dir() / "session.json"


def lock_file() -> Path:
    return state_dir() / "session.lock"


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
    if not _port_open(state.host, state.port):
        return False
    return True


@contextlib.contextmanager
def spawn_lock():
    """Best-effort lock so concurrent CLI invocations don't both spawn a daemon.

    Uses an atomic O_CREAT|O_EXCL file as the lock. Yields True if the
    lock was acquired, False if another process already holds it.
    """
    path = lock_file()
    fd = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        yield True
    except FileExistsError:
        yield False
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
