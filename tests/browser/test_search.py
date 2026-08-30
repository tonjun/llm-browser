"""Tests for llm_browser.browser.search."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import search


@pytest.fixture
def mocks(monkeypatch):
    open_url = MagicMock()
    snap = MagicMock(return_value="snapshot output")
    monkeypatch.setattr(search, "open_url", open_url)
    monkeypatch.setattr(search, "snapshot", snap)
    return open_url, snap


def test_google_builds_query_url(mocks):
    open_url, snap = mocks
    result = search.search("google", "llm browser automation")
    open_url.assert_called_once_with(
        "https://www.google.com/search?q=llm+browser+automation"
    )
    snap.assert_called_once_with(interactive=True, with_urls=True)
    assert result == "snapshot output"


def test_reddit_uses_old_reddit(mocks):
    open_url, _ = mocks
    search.search("reddit", "python")
    open_url.assert_called_once_with("https://old.reddit.com/search/?q=python")


def test_hn_alias(mocks):
    open_url, _ = mocks
    search.search("hackernews", "rust")
    open_url.assert_called_once_with("https://hn.algolia.com/?q=rust")


def test_engine_is_case_insensitive(mocks):
    open_url, _ = mocks
    search.search("GOOGLE", "x")
    open_url.assert_called_once_with("https://www.google.com/search?q=x")


def test_query_is_url_encoded(mocks):
    open_url, _ = mocks
    search.search("bing", "a b&c")
    open_url.assert_called_once_with("https://www.bing.com/search?q=a+b%26c")


def test_unknown_engine_raises(mocks):
    with pytest.raises(ValueError, match="Unknown search engine"):
        search.search("altavista", "x")
