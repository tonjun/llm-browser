"""Tests for llm_browser.browser.state."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import state


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(state, "with_driver", lambda fn: fn(driver))
    return driver


def test_is_visible(d):
    d.is_element_visible.return_value = True
    assert state.is_visible("#a") is True
    d.is_element_visible.assert_called_once_with("#a")


def test_is_checked_delegates_to_safe_helper(d, monkeypatch):
    called = {}

    def fake_safe(drv, sel):
        called["args"] = (drv, sel)
        return True

    monkeypatch.setattr(state, "_is_checked_safe", fake_safe)
    assert state.is_checked("#a") is True
    assert called["args"] == (d, "#a")


def test_is_enabled_true_when_no_disabled_attr(d):
    d.get_attribute.return_value = None
    assert state.is_enabled("#a") is True


def test_is_enabled_false_when_disabled_attr_present(d):
    d.get_attribute.return_value = ""
    assert state.is_enabled("#a") is False


def test_is_visible_resolves_ref(d):
    state.is_visible("@e2")
    d.is_element_visible.assert_called_once_with('[data-llmb-ref="e2"]')
