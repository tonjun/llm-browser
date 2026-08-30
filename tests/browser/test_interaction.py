"""Tests for llm_browser.browser.interaction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import interaction


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(interaction, "with_driver", lambda fn: fn(driver))
    return driver


class TestClick:
    def test_requires_selector_or_text(self):
        with pytest.raises(ValueError, match="click requires"):
            interaction.click()

    def test_clicks_by_selector(self, d):
        interaction.click(selector="#a")
        d.click.assert_called_once_with("#a")

    def test_clicks_by_text(self, d):
        el = MagicMock()
        d.find_element_by_text.return_value = el
        interaction.click(text="Submit")
        d.find_element_by_text.assert_called_once_with("Submit")
        el.click.assert_called_once()

    def test_text_takes_precedence_over_selector(self, d):
        el = MagicMock()
        d.find_element_by_text.return_value = el
        interaction.click(selector="#a", text="Submit")
        d.click.assert_not_called()
        el.click.assert_called_once()

    def test_resolves_ref_selector(self, d):
        interaction.click(selector="@e1")
        d.click.assert_called_once_with('[data-llmb-ref="e1"]')


class TestDblclick:
    def test_dispatches_dblclick_event(self, d):
        interaction.dblclick("#a")
        js = d.evaluate.call_args.args[0]
        assert "dblclick" in js
        assert '"#a"' in js


def test_type_text(d):
    interaction.type_text("#a", "hi")
    d.send_keys.assert_called_once_with("#a", "hi")


def test_fill_clears_then_types(d):
    interaction.fill("#a", "hi")
    d.clear.assert_called_once_with("#a")
    d.type.assert_called_once_with("#a", "hi")


class TestPress:
    def test_press_with_selector(self, d):
        interaction.press("Enter", selector="#a")
        d.press_keys.assert_called_once_with("#a", "Enter")

    def test_press_without_selector_uses_focus(self, d):
        interaction.press("Enter")
        d.press_keys.assert_called_once_with(":focus", "Enter")


def test_hover(d):
    interaction.hover("#a")
    d.hover_element.assert_called_once_with("#a")


def test_focus(d):
    interaction.focus("#a")
    d.focus.assert_called_once_with("#a")


class TestCheck:
    def test_clicks_when_unchecked(self, d, monkeypatch):
        monkeypatch.setattr(interaction, "_is_checked_safe", lambda drv, sel: False)
        interaction.check("#a")
        d.click.assert_called_once_with("#a")

    def test_no_op_when_already_checked(self, d, monkeypatch):
        monkeypatch.setattr(interaction, "_is_checked_safe", lambda drv, sel: True)
        interaction.check("#a")
        d.click.assert_not_called()


class TestUncheck:
    def test_clicks_when_checked(self, d, monkeypatch):
        monkeypatch.setattr(interaction, "_is_checked_safe", lambda drv, sel: True)
        interaction.uncheck("#a")
        d.click.assert_called_once_with("#a")

    def test_no_op_when_already_unchecked(self, d, monkeypatch):
        monkeypatch.setattr(interaction, "_is_checked_safe", lambda drv, sel: False)
        interaction.uncheck("#a")
        d.click.assert_not_called()


class TestSelectOption:
    def test_single_value_uses_native_helper(self, d):
        interaction.select_option("#a", ["x"])
        d.select_option_by_value.assert_called_once_with("#a", "x")
        d.evaluate.assert_not_called()

    def test_multiple_values_uses_js(self, d):
        interaction.select_option("#a", ["x", "y"])
        d.select_option_by_value.assert_not_called()
        js = d.evaluate.call_args.args[0]
        assert '"x"' in js and '"y"' in js
        assert "change" in js


def test_drag(d):
    interaction.drag("#src", "#dst")
    d.drag_and_drop.assert_called_once_with("#src", "#dst")


def test_upload(d):
    el = MagicMock()
    d.find_element.return_value = el
    interaction.upload("#a", ["f1.txt", "f2.txt"])
    el.send_file.assert_called_once_with("f1.txt", "f2.txt")


class TestScroll:
    def test_down(self, d):
        interaction.scroll("down", 100)
        d.scroll_down.assert_called_once_with(100)

    def test_up(self, d):
        interaction.scroll("up", 50)
        d.scroll_up.assert_called_once_with(50)

    def test_left(self, d):
        interaction.scroll("left", 20)
        js = d.evaluate.call_args.args[0]
        assert "scrollBy(-20, 0)" in js

    def test_right(self, d):
        interaction.scroll("right", 20)
        js = d.evaluate.call_args.args[0]
        assert "scrollBy(20, 0)" in js

    def test_unknown_direction_raises(self, d):
        with pytest.raises(ValueError, match="Unknown scroll direction"):
            interaction.scroll("sideways")


def test_scroll_into_view(d):
    interaction.scroll_into_view("#a")
    d.scroll_into_view.assert_called_once_with("#a")


def test_scroll_to_top(d):
    interaction.scroll_to_top()
    d.scroll_to_top.assert_called_once()


def test_scroll_to_bottom(d):
    interaction.scroll_to_bottom()
    d.scroll_to_bottom.assert_called_once()
