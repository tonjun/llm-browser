"""Tests for llm_browser.browser.search."""

from __future__ import annotations

import json
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
    snap.assert_called_once_with(compact=True)
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


@pytest.fixture
def json_mocks(monkeypatch):
    open_url = MagicMock()
    snap = MagicMock()
    driver = MagicMock()
    monkeypatch.setattr(search, "open_url", open_url)
    monkeypatch.setattr(search, "snapshot", snap)
    monkeypatch.setattr(search, "with_driver", lambda fn: fn(driver))
    monkeypatch.setattr(search.time, "sleep", lambda _: None)
    return open_url, snap, driver


def test_json_returns_result_array(json_mocks):
    open_url, snap, driver = json_mocks
    rows = [{"title": "T", "url": "https://a.example/", "snippet": "S"}]
    driver.evaluate.return_value = rows
    out = search.search("google", "q", as_json=True)
    assert json.loads(out) == rows
    open_url.assert_called_once_with("https://www.google.com/search?q=q", quiet=True)
    snap.assert_not_called()


def test_json_polls_until_results_appear(json_mocks):
    _, _, driver = json_mocks
    rows = [{"title": "T", "url": "https://a.example/", "snippet": ""}]
    driver.evaluate.side_effect = [[], None, rows]
    assert json.loads(search.search("bing", "q", as_json=True)) == rows
    assert driver.evaluate.call_count == 3


def test_json_empty_returns_empty_array_and_hints(json_mocks, capsys):
    _, _, driver = json_mocks
    driver.evaluate.return_value = []
    assert search.search("ddg", "q", as_json=True) == "[]"
    assert "without --json" in capsys.readouterr().err


@pytest.mark.parametrize("engine", ["reddit", "hn", "github"])
def test_json_unsupported_engine_raises(json_mocks, engine):
    open_url, _, _ = json_mocks
    with pytest.raises(ValueError, match="--json is not supported"):
        search.search(engine, "x", as_json=True)
    open_url.assert_not_called()


def test_every_extractor_engine_is_a_known_engine():
    assert set(search._EXTRACTORS) <= set(search._ENGINES)
