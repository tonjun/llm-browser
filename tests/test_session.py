"""Tests for llm_browser.session: state-file helpers."""

from __future__ import annotations

import json
import os

import pytest

from llm_browser import session


def test_state_dir_creates_directory(tmp_path):
    path = session.state_dir()
    assert path == tmp_path / ".llm-browser"
    assert path.is_dir()


def test_profile_dir_creates_directory():
    path = session.profile_dir()
    assert path == session.state_dir() / "profile"
    assert path.is_dir()


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
            assert session.lock_file().exists()
        # Lock file is removed after the context exits.
        assert not session.lock_file().exists()

    def test_reports_not_acquired_when_already_locked(self):
        session.lock_file().write_text("999999")
        with session.spawn_lock() as acquired:
            assert acquired is False
        # The pre-existing lock file is left alone by a failed acquire.
        assert session.lock_file().exists()

    def test_removes_lock_file_even_on_exception(self):
        with pytest.raises(RuntimeError), session.spawn_lock() as acquired:
            assert acquired is True
            raise RuntimeError("boom")
        assert not session.lock_file().exists()

    def test_sequential_acquisitions_both_succeed(self):
        with session.spawn_lock() as first:
            assert first is True
        with session.spawn_lock() as second:
            assert second is True
