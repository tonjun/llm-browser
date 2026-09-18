"""Tests for llm_browser.daemon: the persistent-session background process."""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

import pytest

from llm_browser import daemon, session


class TestWaitForChromeExit:
    def test_returns_once_port_closes(self, monkeypatch):
        answers = iter([True, True, False])
        monkeypatch.setattr(daemon.session, "_port_open", lambda h, p: next(answers))
        sleeps = []
        monkeypatch.setattr(daemon.time, "sleep", sleeps.append)
        daemon._wait_for_chrome_exit("127.0.0.1", 9222)
        assert len(sleeps) == 2


class TestRun:
    def test_cleans_up_when_chrome_goes_away(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 9222
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(daemon, "_wait_for_chrome_exit", MagicMock())

        daemon._run(headless=True, headed=False)

        driver.quit.assert_called_once()
        assert session.read_state() is None

    def test_launches_chrome_and_writes_state(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 9222
        chrome = MagicMock(return_value=driver)
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", chrome)
        # The Chrome-liveness wait would block forever - stop once reached.
        monkeypatch.setattr(
            daemon, "_wait_for_chrome_exit", MagicMock(side_effect=SystemExit)
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=True, headed=False)

        chrome.assert_called_once()
        assert chrome.call_args.kwargs["headless"] is True
        assert chrome.call_args.kwargs["headed"] is False
        assert chrome.call_args.kwargs["user_data_dir"] == str(session.profile_dir())

        state = session.read_state()
        assert state is not None
        assert state.port == 9222
        assert state.host == "127.0.0.1"

    def test_launches_chrome_headed(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 9222
        chrome = MagicMock(return_value=driver)
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", chrome)
        monkeypatch.setattr(
            daemon, "_wait_for_chrome_exit", MagicMock(side_effect=SystemExit)
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=False, headed=True)

        assert chrome.call_args.kwargs["headless"] is False
        assert chrome.call_args.kwargs["headed"] is True

    def test_registers_sigterm_and_sigint_handlers(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 1
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(
            daemon, "_wait_for_chrome_exit", MagicMock(side_effect=SystemExit)
        )
        registered = {}

        def fake_signal(sig, handler):
            registered[sig] = handler

        monkeypatch.setattr(daemon.signal, "signal", fake_signal)

        with pytest.raises(SystemExit):
            daemon._run(headless=False, headed=False)

        assert signal.SIGTERM in registered
        assert signal.SIGINT in registered

    def test_shutdown_handler_quits_driver_and_clears_state(self, monkeypatch):
        driver = MagicMock()
        driver.get_rd_port.return_value = 1
        monkeypatch.setattr(daemon.sb_cdp, "Chrome", MagicMock(return_value=driver))
        monkeypatch.setattr(
            daemon, "_wait_for_chrome_exit", MagicMock(side_effect=SystemExit)
        )
        registered = {}
        monkeypatch.setattr(
            daemon.signal,
            "signal",
            lambda sig, handler: registered.setdefault(sig, handler),
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=False, headed=False)

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
        monkeypatch.setattr(
            daemon, "_wait_for_chrome_exit", MagicMock(side_effect=SystemExit)
        )
        registered = {}
        monkeypatch.setattr(
            daemon.signal,
            "signal",
            lambda sig, handler: registered.setdefault(sig, handler),
        )

        with pytest.raises(SystemExit):
            daemon._run(headless=False, headed=False)

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
            daemon,
            "_run",
            lambda headless, headed: called.update(headless=headless, headed=headed),
        )
        monkeypatch.setattr(daemon.sys, "argv", ["daemon", "--headless"])
        daemon.main()
        assert called["headless"] is True
        assert called["headed"] is False

    def test_parses_headed_flag(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            daemon,
            "_run",
            lambda headless, headed: called.update(headless=headless, headed=headed),
        )
        monkeypatch.setattr(daemon.sys, "argv", ["daemon", "--headed"])
        daemon.main()
        assert called["headed"] is True
        assert called["headless"] is False

    def test_defaults_headless_false(self, monkeypatch):
        called = {}
        monkeypatch.setattr(
            daemon,
            "_run",
            lambda headless, headed: called.update(headless=headless, headed=headed),
        )
        monkeypatch.setattr(daemon.sys, "argv", ["daemon"])
        daemon.main()
        assert called["headless"] is False
        assert called["headed"] is False

    def test_rejects_headless_and_headed_together(self, monkeypatch):
        monkeypatch.setattr(daemon.sys, "argv", ["daemon", "--headless", "--headed"])
        with pytest.raises(SystemExit):
            daemon.main()
