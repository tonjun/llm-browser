"""Tests for llm_browser.browser.core: daemon lifecycle & attach plumbing."""

from __future__ import annotations

import contextlib
import signal
from unittest.mock import MagicMock

import pytest

from llm_browser import session
from llm_browser.browser import core

# --------------------------------------------------------------------------
# resolve_selector
# --------------------------------------------------------------------------


class TestResolveSelector:
    def test_plain_css_selector_is_unchanged(self):
        assert core.resolve_selector("#foo .bar") == "#foo .bar"

    def test_ref_is_resolved_to_data_attribute(self):
        assert core.resolve_selector("@e12") == '[data-llmb-ref="e12"]'

    def test_ref_like_but_invalid_is_left_alone(self):
        # Doesn't match the e<digits> shape, so passes through untouched.
        assert core.resolve_selector("@foo") == "@foo"

    def test_empty_string(self):
        assert core.resolve_selector("") == ""


# --------------------------------------------------------------------------
# _js_str
# --------------------------------------------------------------------------


class TestJsStr:
    def test_wraps_in_quotes(self):
        assert core._js_str("hello") == '"hello"'

    def test_escapes_quotes(self):
        assert core._js_str('a"b') == '"a\\"b"'

    def test_escapes_backslash(self):
        assert core._js_str("a\\b") == '"a\\\\b"'


# --------------------------------------------------------------------------
# _is_checked_safe
# --------------------------------------------------------------------------


class TestIsCheckedSafe:
    def test_returns_true_when_checked(self):
        d = MagicMock()
        d.is_checked.return_value = True
        assert core._is_checked_safe(d, "#box") is True
        d.is_checked.assert_called_once_with("#box")

    def test_returns_false_when_unchecked(self):
        d = MagicMock()
        d.is_checked.return_value = False
        assert core._is_checked_safe(d, "#box") is False

    def test_key_error_treated_as_false(self):
        d = MagicMock()
        d.is_checked.side_effect = KeyError("checked")
        assert core._is_checked_safe(d, "#box") is False


# --------------------------------------------------------------------------
# _kill_daemon_group
# --------------------------------------------------------------------------


class TestKillDaemonGroup:
    def test_sends_signal_to_process_group(self, monkeypatch):
        killpg = MagicMock()
        monkeypatch.setattr(core.os, "killpg", killpg)
        core._kill_daemon_group(123, signal.SIGKILL)
        killpg.assert_called_once_with(123, signal.SIGKILL)

    def test_swallows_process_lookup_error(self, monkeypatch):
        monkeypatch.setattr(
            core.os, "killpg", MagicMock(side_effect=ProcessLookupError)
        )
        core._kill_daemon_group(123, signal.SIGTERM)  # should not raise

    def test_swallows_permission_error(self, monkeypatch):
        monkeypatch.setattr(core.os, "killpg", MagicMock(side_effect=PermissionError))
        core._kill_daemon_group(123, signal.SIGTERM)  # should not raise


# --------------------------------------------------------------------------
# _spawn_daemon
# --------------------------------------------------------------------------


class TestSpawnDaemon:
    def test_builds_headless_args(self, monkeypatch):
        popen = MagicMock()
        monkeypatch.setattr(core.subprocess, "Popen", popen)
        core._spawn_daemon(headless=True, headed=False)
        args = popen.call_args.args[0]
        assert args[-1] == "--headless"
        assert args[:-1] == [core.sys.executable, "-m", "llm_browser.daemon"]
        assert popen.call_args.kwargs["start_new_session"] is True

    def test_builds_headed_args(self, monkeypatch):
        popen = MagicMock()
        monkeypatch.setattr(core.subprocess, "Popen", popen)
        core._spawn_daemon(headless=False, headed=True)
        args = popen.call_args.args[0]
        assert args[-1] == "--headed"
        assert args[:-1] == [core.sys.executable, "-m", "llm_browser.daemon"]

    def test_builds_default_args(self, monkeypatch):
        popen = MagicMock()
        monkeypatch.setattr(core.subprocess, "Popen", popen)
        core._spawn_daemon(headless=False, headed=False)
        args = popen.call_args.args[0]
        assert "--headless" not in args
        assert "--headed" not in args
        assert args == [core.sys.executable, "-m", "llm_browser.daemon"]


# --------------------------------------------------------------------------
# _wait_for_daemon
# --------------------------------------------------------------------------


class TestWaitForDaemon:
    def test_returns_state_once_alive(self, monkeypatch):
        state = session.SessionState(pid=1, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        assert core._wait_for_daemon() is state

    def test_raises_on_timeout(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        monkeypatch.setattr(core, "_SPAWN_TIMEOUT", 0.05)
        monkeypatch.setattr(core, "_SPAWN_POLL_INTERVAL", 0.01)
        with pytest.raises(RuntimeError, match="Timed out"):
            core._wait_for_daemon()


# --------------------------------------------------------------------------
# _ensure_daemon
# --------------------------------------------------------------------------


class TestEnsureDaemon:
    def test_returns_existing_alive_state_without_spawning(self, monkeypatch):
        state = session.SessionState(pid=1, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        spawn = MagicMock()
        monkeypatch.setattr(core, "_spawn_daemon", spawn)
        result = core._ensure_daemon(headless=False, headed=False)
        assert result is state
        spawn.assert_not_called()

    def test_spawns_when_no_state_and_lock_acquired(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)

        import contextlib

        @contextlib.contextmanager
        def fake_lock():
            yield True

        monkeypatch.setattr(session, "spawn_lock", fake_lock)
        clear = MagicMock()
        monkeypatch.setattr(session, "clear_state", clear)
        spawn = MagicMock()
        monkeypatch.setattr(core, "_spawn_daemon", spawn)
        new_state = session.SessionState(pid=2, host="h", port=2)
        monkeypatch.setattr(core, "_wait_for_daemon", lambda: new_state)

        result = core._ensure_daemon(headless=True, headed=False)
        assert result is new_state
        spawn.assert_called_once_with(headless=True, headed=False)
        clear.assert_called_once()

    def test_spawns_headed_when_no_state_and_lock_acquired(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)

        import contextlib

        @contextlib.contextmanager
        def fake_lock():
            yield True

        monkeypatch.setattr(session, "spawn_lock", fake_lock)
        monkeypatch.setattr(session, "clear_state", MagicMock())
        spawn = MagicMock()
        monkeypatch.setattr(core, "_spawn_daemon", spawn)
        new_state = session.SessionState(pid=2, host="h", port=2)
        monkeypatch.setattr(core, "_wait_for_daemon", lambda: new_state)

        result = core._ensure_daemon(headless=False, headed=True)
        assert result is new_state
        spawn.assert_called_once_with(headless=False, headed=True)

    def test_kills_stale_daemon_before_respawning(self, monkeypatch):
        stale = session.SessionState(pid=99, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: stale)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)

        import contextlib

        @contextlib.contextmanager
        def fake_lock():
            yield True

        monkeypatch.setattr(session, "spawn_lock", fake_lock)
        monkeypatch.setattr(session, "clear_state", MagicMock())
        monkeypatch.setattr(core, "_spawn_daemon", MagicMock())
        monkeypatch.setattr(core, "_wait_for_daemon", lambda: stale)
        kill = MagicMock()
        monkeypatch.setattr(core, "_kill_daemon_group", kill)

        core._ensure_daemon(headless=False, headed=False)
        kill.assert_called_once_with(99, signal.SIGKILL)

    def test_does_not_spawn_when_lock_not_acquired(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)

        import contextlib

        @contextlib.contextmanager
        def fake_lock():
            yield False

        monkeypatch.setattr(session, "spawn_lock", fake_lock)
        spawn = MagicMock()
        monkeypatch.setattr(core, "_spawn_daemon", spawn)
        winner_state = session.SessionState(pid=3, host="h", port=3)
        monkeypatch.setattr(core, "_wait_for_daemon", lambda: winner_state)

        result = core._ensure_daemon(headless=False, headed=False)
        assert result is winner_state
        spawn.assert_not_called()


# --------------------------------------------------------------------------
# _ensure_target
# --------------------------------------------------------------------------


class TestEnsureTarget:
    def test_does_nothing_when_a_page_target_exists(self, monkeypatch):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        get = MagicMock(return_value=MagicMock(json=lambda: [{"type": "page"}]))
        put = MagicMock()
        monkeypatch.setattr(core.requests, "get", get)
        monkeypatch.setattr(core.requests, "put", put)

        core._ensure_target(state)

        get.assert_called_once_with("http://127.0.0.1:9222/json/list", timeout=5)
        put.assert_not_called()

    def test_creates_a_tab_when_no_page_targets(self, monkeypatch):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        get = MagicMock(
            return_value=MagicMock(json=lambda: [{"type": "background_page"}])
        )
        put = MagicMock()
        monkeypatch.setattr(core.requests, "get", get)
        monkeypatch.setattr(core.requests, "put", put)

        core._ensure_target(state)

        put.assert_called_once_with("http://127.0.0.1:9222/json/new", timeout=5)

    def test_creates_a_tab_when_no_targets_at_all(self, monkeypatch):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        get = MagicMock(return_value=MagicMock(json=list))
        put = MagicMock()
        monkeypatch.setattr(core.requests, "get", get)
        monkeypatch.setattr(core.requests, "put", put)

        core._ensure_target(state)

        put.assert_called_once_with("http://127.0.0.1:9222/json/new", timeout=5)


# --------------------------------------------------------------------------
# open_url
# --------------------------------------------------------------------------


def _patch_attach(monkeypatch, title="Title"):
    """Stand in for core._attach() with a mock driver; returns the driver."""
    driver = MagicMock()
    driver.get_title.return_value = title
    driver.evaluate.return_value = "complete"
    monkeypatch.setattr(core, "_attach", lambda: driver)
    return driver


class TestOpenUrl:
    def test_navigates_via_attach_and_prints_title(self, monkeypatch, capsys):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        driver = _patch_attach(monkeypatch, title="My Page")

        core.open_url("https://example.com", headless=False)

        # Via _attach (honors the `tab switch` pointer), not sb_cdp.Chrome()
        # which navigates the newest tab to about:blank first.
        assert not hasattr(core, "sb_cdp")
        driver.get.assert_called_once_with("https://example.com")
        driver.sleep.assert_not_called()
        driver.quit.assert_not_called()
        assert "My Page" in capsys.readouterr().out

    def test_holds_command_lock_while_navigating(self, monkeypatch):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        driver = _patch_attach(monkeypatch)
        held = []

        @contextlib.contextmanager
        def fake_lock():
            held.append("in")
            yield
            held.append("out")

        monkeypatch.setattr(session, "command_lock", fake_lock)
        driver.get.side_effect = lambda url: held.append("get")

        core.open_url("https://example.com")

        assert held == ["in", "get", "out"]

    def test_warns_when_headless_ignored_for_existing_session(
        self, monkeypatch, capsys
    ):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        # Session already alive before this call.
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        _patch_attach(monkeypatch)

        core.open_url("https://example.com", headless=True)

        err = capsys.readouterr().err
        assert "Note: --headless is ignored" in err

    def test_warns_when_headed_ignored_for_existing_session(self, monkeypatch, capsys):
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        # Session already alive before this call.
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        _patch_attach(monkeypatch)

        core.open_url("https://example.com", headed=True)

        err = capsys.readouterr().err
        assert "Note: --headed is ignored" in err

    def test_no_warning_when_starting_fresh_headless(self, monkeypatch, capsys):
        # No session running yet, so "existing" is False - no warning even
        # with headless=True.
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        _patch_attach(monkeypatch)

        core.open_url("https://example.com", headless=True)

        assert "Note:" not in capsys.readouterr().err

    def test_no_warning_when_starting_fresh_headed(self, monkeypatch, capsys):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        state = session.SessionState(pid=1, host="127.0.0.1", port=9222)
        monkeypatch.setattr(core, "_ensure_daemon", lambda headless, headed: state)
        _patch_attach(monkeypatch)

        core.open_url("https://example.com", headed=True)

        assert "Note:" not in capsys.readouterr().err


class TestWaitForLoad:
    def test_returns_once_ready_state_complete(self, monkeypatch):
        monkeypatch.setattr(core.time, "sleep", lambda s: None)
        d = MagicMock()
        d.evaluate.side_effect = ["loading", "interactive", "complete"]
        core.wait_for_load(d, timeout=5, settle=0)
        assert d.evaluate.call_count == 3

    def test_gives_up_at_timeout(self, monkeypatch):
        monkeypatch.setattr(core.time, "sleep", lambda s: None)
        times = iter([0, 0, 100])
        monkeypatch.setattr(core.time, "monotonic", lambda: next(times))
        d = MagicMock()
        d.evaluate.return_value = "loading"
        core.wait_for_load(d, timeout=1, settle=0)  # must not raise
        assert d.evaluate.call_count == 1


# --------------------------------------------------------------------------
# close_session
# --------------------------------------------------------------------------


class TestCloseSession:
    def test_returns_false_when_no_session(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        clear = MagicMock()
        monkeypatch.setattr(session, "clear_state", clear)
        clear_labels = MagicMock()
        monkeypatch.setattr(session, "clear_labels", clear_labels)
        clear_active = MagicMock()
        monkeypatch.setattr(session, "clear_active_tab", clear_active)

        assert core.close_session() is False
        clear.assert_called_once()
        clear_labels.assert_called_once()
        clear_active.assert_called_once()

    def test_reaps_orphaned_group_when_daemon_dead_but_state_stale(self, monkeypatch):
        # Daemon pid is gone but session.json is still there: its Chrome may
        # be lingering (holding the profile lock), so `close` kills the
        # recorded process group instead of just forgetting about it.
        state = session.SessionState(pid=4242, host="127.0.0.1", port=9222)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        kill_group = MagicMock()
        monkeypatch.setattr(core, "_kill_daemon_group", kill_group)
        monkeypatch.setattr(session, "clear_state", MagicMock())
        monkeypatch.setattr(session, "clear_labels", MagicMock())
        monkeypatch.setattr(session, "clear_active_tab", MagicMock())

        assert core.close_session() is False
        kill_group.assert_called_once_with(4242, signal.SIGKILL)

    def test_sends_sigterm_and_returns_true_on_clean_shutdown(self, monkeypatch):
        state = session.SessionState(pid=42, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        kill = MagicMock()
        monkeypatch.setattr(core.os, "kill", kill)
        monkeypatch.setattr(session, "clear_labels", MagicMock())
        monkeypatch.setattr(session, "clear_active_tab", MagicMock())

        # First call to read_state() in close_session() returns state,
        # the polling loop's calls (via session.read_state) return None
        # immediately to simulate a clean, fast shutdown.
        calls = {"n": 0}

        def fake_read_state():
            calls["n"] += 1
            return state if calls["n"] == 1 else None

        monkeypatch.setattr(session, "read_state", fake_read_state)

        result = core.close_session()
        assert result is True
        kill.assert_called_once_with(42, core.signal.SIGTERM)

    def test_force_kills_on_shutdown_timeout(self, monkeypatch):
        state = session.SessionState(pid=42, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(core.os, "kill", MagicMock())
        monkeypatch.setattr(core, "_SPAWN_TIMEOUT", 0.03)
        monkeypatch.setattr(core, "_SPAWN_POLL_INTERVAL", 0.01)
        kill_group = MagicMock()
        monkeypatch.setattr(core, "_kill_daemon_group", kill_group)
        clear = MagicMock()
        monkeypatch.setattr(session, "clear_state", clear)
        monkeypatch.setattr(session, "clear_labels", MagicMock())
        monkeypatch.setattr(session, "clear_active_tab", MagicMock())

        result = core.close_session()
        assert result is True
        kill_group.assert_called_once_with(42, signal.SIGKILL)
        clear.assert_called_once()

    def test_clears_labels_and_active_tab_on_clean_shutdown(self, monkeypatch):
        state = session.SessionState(pid=42, host="h", port=1)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(core.os, "kill", MagicMock())

        calls = {"n": 0}

        def fake_read_state():
            calls["n"] += 1
            return state if calls["n"] == 1 else None

        monkeypatch.setattr(session, "read_state", fake_read_state)
        clear_labels = MagicMock()
        monkeypatch.setattr(session, "clear_labels", clear_labels)
        clear_active = MagicMock()
        monkeypatch.setattr(session, "clear_active_tab", clear_active)

        core.close_session()
        clear_labels.assert_called_once()
        clear_active.assert_called_once()


# --------------------------------------------------------------------------
# _attach / with_driver
# --------------------------------------------------------------------------


class TestActivePage:
    def test_defaults_to_newest_tab_when_no_pointer(self, monkeypatch):
        monkeypatch.setattr(session, "read_active_tab", lambda: None)
        driver = MagicMock()
        t0, t1 = MagicMock(), MagicMock()
        driver.tabs = [t0, t1]
        assert core._active_page(driver) is t1

    def test_returns_tab_matching_active_pointer(self, monkeypatch):
        monkeypatch.setattr(session, "read_active_tab", lambda: "t0")
        driver = MagicMock()
        t0 = MagicMock(target=MagicMock(target_id="t0"))
        t1 = MagicMock(target=MagicMock(target_id="t1"))
        driver.tabs = [t0, t1]
        assert core._active_page(driver) is t0

    def test_falls_back_and_clears_stale_pointer(self, monkeypatch):
        monkeypatch.setattr(session, "read_active_tab", lambda: "gone")
        clear = MagicMock()
        monkeypatch.setattr(session, "clear_active_tab", clear)
        driver = MagicMock()
        t0 = MagicMock(target=MagicMock(target_id="t0"))
        t1 = MagicMock(target=MagicMock(target_id="t1"))
        driver.tabs = [t0, t1]
        assert core._active_page(driver) is t1
        clear.assert_called_once()


class TestAttach:
    def test_raises_when_no_running_session(self, monkeypatch):
        monkeypatch.setattr(session, "read_state", lambda: None)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: False)
        with pytest.raises(RuntimeError, match="No running session"):
            core._attach()

    def test_attaches_and_opens_last_tab(self, monkeypatch):
        state = session.SessionState(pid=1, host="h", port=1)
        monkeypatch.setattr(session, "read_state", lambda: state)
        monkeypatch.setattr(session, "is_daemon_alive", lambda s: True)
        monkeypatch.setattr(session, "read_active_tab", lambda: None)
        monkeypatch.setattr(core, "_ensure_target", MagicMock())

        from unittest.mock import AsyncMock

        page = MagicMock()
        page.aopen = AsyncMock(return_value=None)
        driver = MagicMock()
        driver.tabs = [MagicMock(), page]
        start_sync = MagicMock(return_value=driver)
        monkeypatch.setattr(core.cdp_util, "start_sync", start_sync)

        class FakeCDPMethods:
            def __init__(self, loop, page, driver):
                self.loop = loop
                self.page = page
                self.driver = driver

        monkeypatch.setattr(core, "CDPMethods", FakeCDPMethods)

        result = core._attach()

        start_sync.assert_called_once()
        assert start_sync.call_args.kwargs["host"] == "h"
        assert start_sync.call_args.kwargs["port"] == 1
        assert result.page is page
        assert result.driver is driver


class TestWithDriver:
    def test_calls_fn_with_attached_driver(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(core, "_attach", lambda: sentinel)
        fn = MagicMock(return_value="result")
        assert core.with_driver(fn) == "result"
        fn.assert_called_once_with(sentinel)

    def test_holds_command_lock_while_fn_runs(self, monkeypatch):
        """Regression test for the tab-new --extract hang: two concurrent
        invocations must not both be attached to the daemon at once."""
        monkeypatch.setattr(core, "_attach", lambda: MagicMock())

        def fn(_d):
            # The lock must already be held (reentrantly) here.
            with session.command_lock():
                pass
            return "ok"

        assert core.with_driver(fn) == "ok"

    def test_releases_command_lock_even_on_exception(self, monkeypatch):
        monkeypatch.setattr(core, "_attach", lambda: MagicMock())
        with pytest.raises(RuntimeError):
            core.with_driver(lambda _d: (_ for _ in ()).throw(RuntimeError("boom")))
        # Lock must be free again - this would hang if it leaked.
        with session.command_lock():
            pass


# --------------------------------------------------------------------------
# _patch_cdp_send_timeout
# --------------------------------------------------------------------------


class TestPatchCdpSendTimeout:
    def test_is_idempotent(self):
        before = core.Connection.send
        core._patch_cdp_send_timeout()
        assert core.Connection.send is before

    def test_times_out_instead_of_hanging(self, monkeypatch):
        """Simulates the actual hang: a CDP command whose response never
        arrives (e.g. because the tab it was sent to got closed) must
        surface as a TimeoutError, not wedge the caller forever."""
        import asyncio

        from seleniumbase.undetected.cdp_driver.connection import Connection

        conn = Connection.__new__(Connection)
        orig_send = Connection.send

        async def _never_returns(self, cdp_obj, _is_update=True):
            await asyncio.Future()  # never resolves, like a dead websocket

        # Install the never-returning "vendored original", then re-run our
        # patch on top of it so this exercises the real wrapper logic.
        type.__setattr__(Connection, "send", _never_returns)
        monkeypatch.setattr(core, "_cdp_send_patched", False)
        monkeypatch.setattr(core, "_CDP_COMMAND_TIMEOUT", 0.05)
        try:
            core._patch_cdp_send_timeout()
            with pytest.raises(TimeoutError, match="timed out"):
                asyncio.run(conn.send(None))
        finally:
            type.__setattr__(Connection, "send", orig_send)
