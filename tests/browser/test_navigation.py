"""Tests for llm_browser.browser.navigation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import navigation


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(navigation, "with_driver", lambda fn: fn(driver))
    return driver


def test_go_back(d):
    navigation.go_back()
    d.go_back.assert_called_once()


def test_go_forward(d):
    navigation.go_forward()
    d.go_forward.assert_called_once()


def test_reload_default(d):
    navigation.reload_page()
    d.reload.assert_called_once_with(ignore_cache=False)


def test_reload_ignore_cache(d):
    navigation.reload_page(ignore_cache=True)
    d.reload.assert_called_once_with(ignore_cache=True)
