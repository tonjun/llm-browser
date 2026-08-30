"""Tests for llm_browser.browser.info: read-only page/element getters."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import info


@pytest.fixture
def d(monkeypatch):
    """A fake CDPMethods driver wired up as the attach target."""
    driver = MagicMock()
    monkeypatch.setattr(info, "with_driver", lambda fn: fn(driver))
    return driver


def test_get_text(d):
    d.get_text.return_value = "hello"
    assert info.get_text("#a") == "hello"
    d.get_text.assert_called_once_with("#a")


def test_get_text_resolves_ref(d):
    info.get_text("@e3")
    d.get_text.assert_called_once_with('[data-llmb-ref="e3"]')


def test_get_html(d):
    d.get_element_html.return_value = "<div></div>"
    assert info.get_html("#a") == "<div></div>"


def test_get_value(d):
    d.get_attribute.return_value = "foo"
    assert info.get_value("#a") == "foo"
    d.get_attribute.assert_called_once_with("#a", "value")


def test_get_attr(d):
    d.get_attribute.return_value = "bar"
    assert info.get_attr("#a", "data-x") == "bar"
    d.get_attribute.assert_called_once_with("#a", "data-x")


def test_get_title(d):
    d.get_title.return_value = "Page"
    assert info.get_title() == "Page"


def test_get_url(d):
    d.get_current_url.return_value = "https://x"
    assert info.get_url() == "https://x"


def test_get_count(d):
    d.find_elements.return_value = [1, 2, 3]
    assert info.get_count("#a") == 3


def test_get_count_zero(d):
    d.find_elements.return_value = []
    assert info.get_count("#a") == 0


def test_get_box(d):
    d.get_element_rect.return_value = {"x": 1, "y": 2}
    assert info.get_box("#a") == {"x": 1, "y": 2}


def test_get_styles_all(d):
    d.evaluate.return_value = "{}"
    info.get_styles("#a")
    js = d.evaluate.call_args.args[0]
    assert "getComputedStyle" in js
    assert 'querySelector("#a")' in js


def test_get_styles_single_prop(d):
    d.evaluate.return_value = "10px"
    result = info.get_styles("#a", prop="color")
    assert result == "10px"
    js = d.evaluate.call_args.args[0]
    assert 'getPropertyValue("color")' in js


def test_get_cdp_url(d):
    d.get_websocket_url.return_value = "ws://x"
    assert info.get_cdp_url() == "ws://x"
