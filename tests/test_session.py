"""Tests for llm_browser.session: state-file helpers."""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time

import pytest

from llm_browser import session


def test_state_dir_creates_directory(tmp_path):
    path = session.state_dir()
    assert path == tmp_path / ".llm-browser"
    assert path.is_dir()


def test_state_dir_honors_home_env_var(tmp_path, monkeypatch):
    custom = tmp_path / "agent-2"
    monkeypatch.setenv("LLM_BROWSER_HOME", str(custom))
    assert session.state_dir() == custom
    assert custom.is_dir()
    # Everything else hangs off it, so the profile moves too.
    assert session.profile_dir() == custom / "profile"


def test_profile_dir_creates_directory():
    path = session.profile_dir()
    assert path == session.state_dir() / "profile"
    assert path.is_dir()


def test_screenshots_and_pages_dirs_are_created_under_state_dir():
    assert session.screenshots_dir() == session.state_dir() / "screenshots"
    assert session.screenshots_dir().is_dir()
    assert session.pages_dir() == session.state_dir() / "pages"
    assert session.pages_dir().is_dir()


def test_log_file_path():
    assert session.log_file() == session.state_dir() / "daemon.log"


def test_session_file_path():
    assert session.session_file() == session.state_dir() / "session.json"


def test_lock_file_path():
    assert session.lock_file() == session.state_dir() / "session.lock"


class TestReadState:
    def test_returns_none_when_missing(self):
        assert session.read_state() is None

    def test_returns_none_on_invalid_json(self):
        session.session_file().write_text("not json")
        assert session.read_state() is None

    def test_returns_none_on_missing_keys(self):
        session.session_file().write_text(json.dumps({"pid": 1}))
        assert session.read_state() is None

    def test_reads_valid_state(self):
        session.session_file().write_text(
            json.dumps({"pid": 123, "host": "127.0.0.1", "port": 9222})
        )
        state = session.read_state()
        assert state == session.SessionState(pid=123, host="127.0.0.1", port=9222)


class TestWriteState:
    def test_write_then_read_round_trips(self):
        session.write_state(pid=42, host="localhost", port=1234)
        state = session.read_state()
        assert state == session.SessionState(pid=42, host="localhost", port=1234)

    def test_overwrites_existing_state(self):
        session.write_state(pid=1, host="a", port=1)
        session.write_state(pid=2, host="b", port=2)
        state = session.read_state()
        assert state == session.SessionState(pid=2, host="b", port=2)


class TestClearState:
    def test_removes_existing_state_file(self):
        session.write_state(pid=1, host="a", port=1)
        session.clear_state()
        assert not session.session_file().exists()
        assert session.read_state() is None

    def test_no_error_when_no_state_file(self):
        session.clear_state()  # should not raise


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert session._pid_alive(os.getpid()) is True

    def test_nonexistent_pid_is_not_alive(self):
        # A pid that (almost certainly) doesn't exist.
        assert session._pid_alive(2**30) is False

    def test_permission_error_counts_as_alive(self, monkeypatch):
        def _raise_permission_error(pid, sig):
            raise PermissionError

        monkeypatch.setattr(session.os, "kill", _raise_permission_error)
        assert session._pid_alive(1) is True


class TestPortOpen:
    def test_open_port_returns_true(self):
        import socket

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        try:
            host, port = srv.getsockname()
            assert session._port_open(host, port) is True
        finally:
            srv.close()

    def test_closed_port_returns_false(self):
        import socket

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        host, port = srv.getsockname()
        srv.close()  # port is now free/closed
        assert session._port_open(host, port, timeout=0.2) is False


class TestIsDaemonAlive:
    def test_none_state_is_not_alive(self):
        assert session.is_daemon_alive(None) is False

    def test_dead_pid_is_not_alive(self, monkeypatch):
        monkeypatch.setattr(session, "_pid_alive", lambda pid: False)
        state = session.SessionState(pid=1, host="h", port=1)
        assert session.is_daemon_alive(state) is False

    def test_alive_pid_but_closed_port_is_not_alive(self, monkeypatch):
        monkeypatch.setattr(session, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(
            session, "_port_open", lambda host, port, timeout=0.5: False
        )
        state = session.SessionState(pid=1, host="h", port=1)
        assert session.is_daemon_alive(state) is False

    def test_alive_pid_and_open_port_is_alive(self, monkeypatch):
        monkeypatch.setattr(session, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(session, "_port_open", lambda host, port, timeout=0.5: True)
        state = session.SessionState(pid=1, host="h", port=1)
        assert session.is_daemon_alive(state) is True


class TestSpawnLock:
    def test_acquires_lock_when_free(self):
        with session.spawn_lock() as acquired:
            assert acquired is True

    def test_reports_not_acquired_when_already_locked(self):
        # Hold the flock from a separate fd, as another process would.
        fd = os.open(session.lock_file(), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with session.spawn_lock() as acquired:
                assert acquired is False
        finally:
            os.close(fd)

    def test_stale_lock_file_from_dead_holder_does_not_block(self):
        # A leftover file (e.g. from a process killed mid-spawn) carries no
        # lock once its holder is gone, so the next acquire must succeed.
        session.lock_file().write_text("999999")
        with session.spawn_lock() as acquired:
            assert acquired is True

    def test_released_even_on_exception(self):
        with pytest.raises(RuntimeError), session.spawn_lock() as acquired:
            assert acquired is True
            raise RuntimeError("boom")
        with session.spawn_lock() as again:
            assert again is True

    def test_sequential_acquisitions_both_succeed(self):
        with session.spawn_lock() as first:
            assert first is True
        with session.spawn_lock() as second:
            assert second is True


class TestCommandLock:
    def test_command_lock_file_path(self):
        assert session.command_lock_file() == session.state_dir() / "command.lock"

    def test_is_reentrant_within_one_thread(self):
        """A caller already holding it (e.g. tab_new_extract wrapping
        several with_driver calls) can take it again without deadlocking
        on itself."""
        with session.command_lock(), session.command_lock():
            pass  # would hang here if it weren't reentrant

    def test_released_even_on_exception(self):
        with pytest.raises(RuntimeError), session.command_lock():
            raise RuntimeError("boom")
        # A fresh acquisition afterwards must not block.
        done = threading.Event()

        def _acquire():
            with session.command_lock():
                done.set()

        t = threading.Thread(target=_acquire, daemon=True)
        t.start()
        t.join(timeout=2)
        assert done.is_set()

    def test_serializes_concurrent_holders(self):
        """The core fix for the reported hang: a second holder blocks
        until the first releases, instead of both racing the daemon's
        shared active-tab state at once."""
        order: list[str] = []
        first_acquired = threading.Event()

        def _first():
            with session.command_lock():
                order.append("first-acquired")
                first_acquired.set()
                time.sleep(0.2)
                order.append("first-released")

        def _second():
            # Only attempt once the first thread definitely holds the
            # lock, so this necessarily has to block on it (rather than
            # the outcome depending on which thread happens to get
            # scheduled first).
            first_acquired.wait(timeout=2)
            with session.command_lock():
                order.append("second-acquired")

        t1 = threading.Thread(target=_first)
        t2 = threading.Thread(target=_second)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert not t1.is_alive() and not t2.is_alive()
        assert order == ["first-acquired", "first-released", "second-acquired"]
