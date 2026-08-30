"""Tests for llm_browser.browser.misc."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import misc


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(misc, "with_driver", lambda fn: fn(driver))
    return driver


def test_highlight(d):
    misc.highlight("#a")
    d.highlight.assert_called_once_with("#a")


def test_is_online(d):
    d.is_online.return_value = True
    assert misc.is_online() is True


class TestReadPage:
    def test_whole_page(self, d):
        soup = MagicMock()
        soup.get_text.return_value = "all text"
        d.get_beautiful_soup.return_value = soup
        assert misc.read_page() == "all text"
        soup.get_text.assert_called_once_with(" ", strip=True)

    def test_scoped_to_selector(self, d):
        node = MagicMock()
        node.get_text.return_value = "scoped text"
        soup = MagicMock()
        soup.select_one.return_value = node
        d.get_beautiful_soup.return_value = soup
        assert misc.read_page("#a") == "scoped text"
        soup.select_one.assert_called_once_with("#a")

    def test_selector_matches_nothing_returns_empty(self, d):
        soup = MagicMock()
        soup.select_one.return_value = None
        d.get_beautiful_soup.return_value = soup
        assert misc.read_page("#missing") == ""


def test_internalize_links(d):
    misc.internalize_links()
    d.internalize_links.assert_called_once()


def test_tile_windows(d):
    misc.tile_windows()
    d.tile_windows.assert_called_once()


def test_mfa_code(d):
    d.get_mfa_code.return_value = "123456"
    assert misc.mfa_code("SECRET") == "123456"
    d.get_mfa_code.assert_called_once_with("SECRET")


def test_enter_mfa(d):
    misc.enter_mfa("#a", "SECRET")
    d.enter_mfa_code.assert_called_once_with("#a", "SECRET")


def test_enter_mfa_resolves_ref(d):
    misc.enter_mfa("@e5", None)
    d.enter_mfa_code.assert_called_once_with('[data-llmb-ref="e5"]', None)
