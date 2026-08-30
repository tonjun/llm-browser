"""Tests for llm_browser.browser.evaluate."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import evaluate as evaluate_mod


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(evaluate_mod, "with_driver", lambda fn: fn(driver))
    return driver


def test_evaluate_runs_js_and_returns_result(d):
    d.evaluate.return_value = 42
    assert evaluate_mod.evaluate("1 + 41") == 42
    d.evaluate.assert_called_once_with("1 + 41")
