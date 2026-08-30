"""Tests for llm_browser.browser.extract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_browser.browser import extract


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    driver.get_page_source.return_value = "<html>...</html>"
    driver.get_current_url.return_value = "https://example.com"
    monkeypatch.setattr(extract, "with_driver", lambda fn: fn(driver))
    return driver


def test_extract_markdown_default(d, monkeypatch):
    calls = {}

    def fake_extract(html, url=None, output_format=None):
        calls["output_format"] = output_format
        return "# Title\n\nBody."

    monkeypatch.setattr(extract.trafilatura, "extract", fake_extract)
    result = extract.extract_content()
    assert result == "# Title\n\nBody."
    assert calls["output_format"] == "markdown"


def test_extract_text_mode(d, monkeypatch):
    calls = {}

    def fake_extract(html, url=None, output_format=None):
        calls["output_format"] = output_format
        return "Title Body."

    monkeypatch.setattr(extract.trafilatura, "extract", fake_extract)
    result = extract.extract_content(markdown=False)
    assert result == "Title Body."
    assert calls["output_format"] == "txt"


def test_extract_falls_back_to_page_text(d, monkeypatch):
    monkeypatch.setattr(extract.trafilatura, "extract", lambda *a, **k: None)
    soup = MagicMock()
    soup.get_text.return_value = "fallback text"
    d.get_beautiful_soup.return_value = soup
    result = extract.extract_content()
    assert result == "fallback text"


class TestSaveMarkdown:
    def test_explicit_path_writes_content(self, d, monkeypatch, tmp_path):
        monkeypatch.setattr(
            extract.trafilatura, "extract", lambda *a, **k: "# Title\n\nBody."
        )
        target = tmp_path / "out.md"
        result = extract.save_markdown(str(target))
        assert result == str(target)
        assert target.read_text() == "# Title\n\nBody."

    def test_no_path_generates_one_under_state_dir(self, d, monkeypatch):
        monkeypatch.setattr(extract.trafilatura, "extract", lambda *a, **k: "content")
        from llm_browser import session

        result = extract.save_markdown()
        try:
            assert result.startswith(str(session.state_dir()))
            assert result.endswith(".md")
            assert Path(result).read_text() == "content"
        finally:
            Path(result).unlink(missing_ok=True)
