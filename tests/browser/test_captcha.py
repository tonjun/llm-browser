"""Tests for llm_browser.browser.captcha."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import captcha


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(captcha, "with_driver", lambda fn: fn(driver))
    return driver


def test_solve_captcha_default_uses_cdp_path(d):
    d.solve_captcha.return_value = True
    assert captcha.solve_captcha() is True
    d.solve_captcha.assert_called_once()
    d.gui_click_captcha.assert_not_called()


def test_solve_captcha_gui_uses_gui_path(d):
    d.gui_click_captcha.return_value = False
    assert captcha.solve_captcha(gui=True) is False
    d.gui_click_captcha.assert_called_once()
    d.solve_captcha.assert_not_called()
