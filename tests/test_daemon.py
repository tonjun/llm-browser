"""Tests for llm_browser.daemon: the persistent-session background process."""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

import pytest

from llm_browser import daemon, session


class TestRun:
    def test_launches_chrome_and_writes_state(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 9222
        chrome = MagicMock(return_value=driver)
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", chrome)
        # signal.pause() would block forever - stop right after it's called.
        monkeypatch.setattr(daemon.signal, "pause", MagicMock(side_effect=SystemExit))

        with pytest.raises(SystemExit):
            daemon._run(headless=True)

        chrome.assert_called_once()
        assert chrome.call_args.kwargs["headless"] is True
        assert chrome.call_args.kwargs["user_data_dir"] == str(session.profile_dir())

        state = session.read_state()
        assert state is not None
        assert state.port == 9222
        assert state.host == "127.0.0.1"

    def test_registers_sigterm_and_sigint_handlers(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 1
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(daemon.signal, "pause", MagicMock(side_effect=SystemExit))
        registered = {}

        def fake_signal(sig, handler):
            registered[sig] = handler

        monkeypatch.setattr(daemon.signal, "signal", fake_signal)

        with pytest.raises(SystemExit):
            daemon._run(headless=False)

        assert signal.SIGTERM in registered
        assert signal.SIGINT in registered

    def test_shutdown_handler_quits_driver_and_clears_state(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 1
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(daemon.signal, "pause", MagicMock(side_effect=SystemExit))
        registered = {}
        monkeypatch.setattr(
            daemon.signal,
            "signal",
            lambda sig, handler: registered.setdefault(sig, handler),
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=False)

        session.write_state(pid=1, host="h", port=1)
        with pytest.raises(SystemExit):
            registered[signal.SIGTERM](signal.SIGTERM, None)

        driver.quit.assert_called_once()
        assert session.read_state() is None

    def test_shutdown_handler_clears_state_even_if_quit_raises(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 1
        driver.quit.side_effect = RuntimeError("boom")
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(daemon.signal, "pause", MagicMock(side_effect=SystemExit))
        registered = {}
        monkeypatch.setattr(
            daemon.signal,
            "signal",
            lambda sig, handler: registered.setdefault(sig, handler),
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=False)

        session.write_state(pid=1, host="h", port=1)
        # quit() raising propagates past the `finally` (sys.exit() is
        # never reached), but the `finally` still clears state on the
        # way out.
        with pytest.raises(RuntimeError, match="boom"):
            registered[signal.SIGTERM](signal.SIGTERM, None)

        assert session.read_state() is None


class TestMain:
    def test_parses_headless_flag(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            daemon, "_run", lambda headless: called.setdefault("headless", headless)
        )
        monkeypatch.setattr(daemon.sys, "argv", ["daemon", "--headless"])
        daemon.main()
        assert called["headless"] is True

    def test_defaults_headless_false(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            daemon, "_run", lambda headless: called.setdefault("headless", headless)
        )
        monkeypatch.setattr(daemon.sys, "argv", ["daemon"])
        daemon.main()
        assert called["headless"] is False
