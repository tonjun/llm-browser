"""Tests for llm_browser.browser.tabs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import tabs


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(tabs, "with_driver", lambda fn: fn(driver))
    return driver


def test_tab_new_with_url(d):
    tabs.tab_new("https://example.com")
    d.open_new_tab.assert_called_once_with("https://example.com")


def test_tab_new_without_url(d):
    tabs.tab_new()
    d.open_new_tab.assert_called_once_with(None)


class TestTabList:
    def test_lists_tabs_with_index_url_title(self, d):
        t0 = MagicMock(target=MagicMock(url="https://a", title="A"))
        t1 = MagicMock(target=MagicMock(url="https://b", title="B"))
        d.get_tabs.return_value = [t0, t1]
        result = tabs.tab_list()
        assert result == [
            {"index": 0, "url": "https://a", "title": "A"},
            {"index": 1, "url": "https://b", "title": "B"},
        ]

    def test_missing_target_yields_none_fields(self, d):
        t0 = MagicMock(spec=[])  # no `target` attribute at all
        d.get_tabs.return_value = [t0]
        result = tabs.tab_list()
        assert result == [{"index": 0, "url": None, "title": None}]

    def test_empty_tabs(self, d):
        d.get_tabs.return_value = []
        assert tabs.tab_list() == []


def test_tab_switch(d):
    tabs.tab_switch(2)
    d.switch_to_tab.assert_called_once_with(2)


class TestTabClose:
    def test_close_with_index_switches_first(self, d):
        tabs.tab_close(1)
        d.switch_to_tab.assert_called_once_with(1)
        d.close_active_tab.assert_called_once()

    def test_close_without_index_closes_current(self, d):
        tabs.tab_close()
        d.switch_to_tab.assert_not_called()
        d.close_active_tab.assert_called_once()


def test_window_new(d):
    tabs.window_new("https://x")
    d.open_new_window.assert_called_once_with("https://x")


class TestTabNewExtract:
    @pytest.fixture(autouse=True)
    def _extract(self, d, monkeypatch):
        # tab_new_extract calls extract.extract_content(), which attaches
        # via its own `with_driver` - point it at the same mock driver.
        monkeypatch.setattr(tabs.extract, "with_driver", lambda fn: fn(d))
        monkeypatch.setattr(
            tabs.extract.trafilatura, "extract", lambda *a, **k: "# Title\n\nBody."
        )
        return d

    def test_opens_and_extracts(self, d):
        result = tabs.tab_new_extract("https://example.com")
        d.open_new_tab.assert_called_once_with("https://example.com")
        assert result == "# Title\n\nBody."

    def test_does_not_close_by_default(self, d):
        tabs.tab_new_extract("https://example.com")
        d.close_active_tab.assert_not_called()

    def test_close_true_closes_after_extracting(self, d):
        tabs.tab_new_extract("https://example.com", close=True)
        d.close_active_tab.assert_called_once()
