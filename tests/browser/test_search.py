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


def _row(n: int) -> dict[str, str]:
    return {"title": f"T{n}", "url": f"https://a.example/{n}", "snippet": ""}


@pytest.mark.parametrize(
    "engine, base, suffixes",
    [
        ("google", "https://www.google.com/search?q=q", ["", "&start=10", "&start=20"]),
        ("bing", "https://www.bing.com/search?q=q", ["", "&first=11", "&first=21"]),
    ],
)
def test_pages_builds_per_page_urls(json_mocks, engine, base, suffixes):
    open_url, _, driver = json_mocks
    driver.evaluate.side_effect = [[_row(1)], [_row(2)], [_row(3)]]
    out = search.search(engine, "q", as_json=True, pages=3)
    assert json.loads(out) == [_row(1), _row(2), _row(3)]
    assert [c.args[0] for c in open_url.call_args_list] == [base + s for s in suffixes]
    assert all(c.kwargs == {"quiet": True} for c in open_url.call_args_list)


def test_pages_dedupes_across_pages(json_mocks):
    _, _, driver = json_mocks
    driver.evaluate.side_effect = [[_row(1), _row(2)], [_row(2), _row(3)]]
    out = search.search("google", "q", as_json=True, pages=2)
    assert json.loads(out) == [_row(1), _row(2), _row(3)]


def test_pages_stops_early_when_page_adds_nothing_new(json_mocks, capsys):
    open_url, _, driver = json_mocks
    driver.evaluate.side_effect = [[_row(1)], [_row(1)]] + [[_row(1)]] * 50
    out = search.search("google", "q", as_json=True, pages=4)
    assert json.loads(out) == [_row(1)]
    assert open_url.call_count == 2
    assert "page 2" in capsys.readouterr().err


def test_pages_greater_than_one_requires_json(mocks):
    open_url, _ = mocks
    with pytest.raises(ValueError, match="requires --json"):
        search.search("google", "q", pages=2)
    open_url.assert_not_called()


@pytest.mark.parametrize("engine", ["duckduckgo", "ddg"])
def test_pages_unsupported_engine_raises(json_mocks, engine):
    open_url, _, _ = json_mocks
    with pytest.raises(ValueError, match="--pages is not supported"):
        search.search(engine, "q", as_json=True, pages=2)
    open_url.assert_not_called()


def test_every_page_engine_has_an_extractor():
    assert set(search._PAGE_PARAMS) <= set(search._EXTRACTORS)


def test_every_extractor_engine_is_a_known_engine():
    assert set(search._EXTRACTORS) <= set(search._ENGINES)
