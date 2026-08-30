"""Tests for llm_browser.browser.gui."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import gui


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(gui, "with_driver", lambda fn: fn(driver))
    return driver


def test_gui_click(d):
    gui.gui_click("#a")
    d.gui_click_element.assert_called_once_with("#a")


def test_gui_click_resolves_ref(d):
    gui.gui_click("@e1")
    d.gui_click_element.assert_called_once_with('[data-llmb-ref="e1"]')


def test_gui_hover_and_click(d):
    gui.gui_hover_and_click("#h", "#c")
    d.gui_hover_and_click.assert_called_once_with("#h", "#c")


def test_gui_drag(d):
    gui.gui_drag("#src", "#dst")
    d.gui_drag_and_drop.assert_called_once_with("#src", "#dst")
