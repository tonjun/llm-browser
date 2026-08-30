"""Tests for llm_browser.browser.wait."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import wait as wait_mod


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(wait_mod, "with_driver", lambda fn: fn(driver))
    return driver


def test_wait_ms_sleeps_seconds(d):
    wait_mod.wait_for(ms=1500)
    d.sleep.assert_called_once_with(1.5)


def test_wait_selector(d):
    wait_mod.wait_for(selector="#a", timeout=5.0)
    d.wait_for_element.assert_called_once_with("#a", timeout=5.0)


def test_wait_selector_resolves_ref(d):
    wait_mod.wait_for(selector="@e1")
    d.wait_for_element.assert_called_once_with('[data-llmb-ref="e1"]', timeout=25.0)


def test_wait_text(d):
    wait_mod.wait_for(text="Loaded", timeout=3.0)
    d.wait_for_text.assert_called_once_with("Loaded", selector="body", timeout=3.0)


class TestWaitUrl:
    def test_returns_once_url_matches_glob(self, d):
        d.get_current_url.return_value = "https://example.com/done"
        wait_mod.wait_for(url="*/done", timeout=1.0)
        d.sleep.assert_not_called()

    def test_polls_until_match(self, d):
        urls = iter(["https://x/a", "https://x/a", "https://x/done"])
        d.get_current_url.side_effect = lambda: next(urls)
        wait_mod.wait_for(url="*/done", timeout=5.0)
        assert d.sleep.call_count == 2

    def test_times_out(self, d):
        d.get_current_url.return_value = "https://x/never"
        with pytest.raises(TimeoutError, match="Timed out waiting for URL"):
            wait_mod.wait_for(url="*/done", timeout=0.05)


class TestWaitJsFn:
    def test_returns_once_truthy(self, d):
        d.evaluate.return_value = True
        wait_mod.wait_for(js_fn="true", timeout=1.0)
        d.sleep.assert_not_called()

    def test_polls_until_truthy(self, d):
        results = iter([False, False, True])
        d.evaluate.side_effect = lambda js: next(results)
        wait_mod.wait_for(js_fn="cond", timeout=5.0)
        assert d.sleep.call_count == 2

    def test_times_out(self, d):
        d.evaluate.return_value = False
        with pytest.raises(TimeoutError, match="Timed out waiting for condition"):
            wait_mod.wait_for(js_fn="cond", timeout=0.05)


def test_wait_requires_one_argument(d):
    with pytest.raises(ValueError, match="wait requires one of"):
        wait_mod.wait_for()
