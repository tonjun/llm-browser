"""Tests for llm_browser.browser.fetch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import fetch


@pytest.fixture
def mock_requests(monkeypatch):
    resp = MagicMock()
    resp.text = "<html><body><p>hello</p></body></html>"
    resp.raise_for_status = MagicMock()
    get = MagicMock(return_value=resp)
    monkeypatch.setattr(fetch.requests, "get", get)
    return get, resp


def test_fetch_url_sends_request_with_ua_and_timeout(mock_requests, monkeypatch):
    get, _ = mock_requests
    monkeypatch.setattr(fetch.trafilatura, "extract", lambda *a, **k: "extracted text")
    fetch.fetch_url("https://example.com")
    get.assert_called_once_with(
        "https://example.com", timeout=15, headers={"User-Agent": fetch._UA}
    )


def test_fetch_url_raises_for_status(mock_requests):
    _, resp = mock_requests
    resp.raise_for_status.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        fetch.fetch_url("https://example.com")


def test_fetch_url_text_format(mock_requests, monkeypatch):
    calls = {}

    def fake_extract(html, url=None, output_format=None):
        calls["output_format"] = output_format
        return "plain text"

    monkeypatch.setattr(fetch.trafilatura, "extract", fake_extract)
    result = fetch.fetch_url("https://example.com")
    assert result == "plain text"
    assert calls["output_format"] == "txt"


def test_fetch_url_markdown_format(mock_requests, monkeypatch):
    calls = {}

    def fake_extract(html, url=None, output_format=None):
        calls["output_format"] = output_format
        return "# heading"

    monkeypatch.setattr(fetch.trafilatura, "extract", fake_extract)
    result = fetch.fetch_url("https://example.com", markdown=True)
    assert result == "# heading"
    assert calls["output_format"] == "markdown"


def test_fetch_url_falls_back_to_raw_text_when_extract_fails(
    mock_requests, monkeypatch
):
    monkeypatch.setattr(fetch.trafilatura, "extract", lambda *a, **k: None)
    result = fetch.fetch_url("https://example.com")
    assert result == "<html><body><p>hello</p></body></html>"
