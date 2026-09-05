"""Tests for llm_browser.browser.interaction."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

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
    @pytest.fixture
    def d(self, monkeypatch):
        # These need a real event loop: unlike the module-level `d`
        # fixture's plain MagicMock, `_dispatch_key_combo` builds a
        # coroutine and hands it to `d.loop.run_until_complete` - a mocked
        # loop would just swallow that coroutine object without ever
        # running it, so `d.page.send` would never actually be awaited.
        driver = MagicMock()
        driver.loop = asyncio.new_event_loop()
        driver.page.send = AsyncMock(return_value=None)
        monkeypatch.setattr(interaction, "with_driver", lambda fn: fn(driver))
        yield driver
        driver.loop.close()

    def _sent_events(self, d):
        # Each call.args[0] is the generator mycdp.input_.dispatch_key_event()
        # returns; advancing it once yields the {"method", "params"} dict
        # that would actually go out over the CDP websocket.
        return [next(call.args[0])["params"] for call in d.page.send.call_args_list]

    def test_press_enter_dispatches_key_event_not_literal_text(self, d):
        # Regression: press("Enter") must not type the literal characters
        # "E", "n", "t", "e", "r" into the focused element.
        interaction.press("Enter")
        events = self._sent_events(d)
        assert len(events) == 2  # keyDown, keyUp
        assert all(e["key"] == "Enter" for e in events)
        assert [e["type"] for e in events] == ["keyDown", "keyUp"]

    def test_press_with_selector_focuses_first(self, d):
        interaction.press("Enter", selector="#a")
        d.focus.assert_called_once_with("#a")

    def test_press_without_selector_does_not_focus(self, d):
        interaction.press("Enter")
        d.focus.assert_not_called()

    def test_press_resolves_ref_selector(self, d):
        interaction.press("Enter", selector="@e1")
        d.focus.assert_called_once_with('[data-llmb-ref="e1"]')

    def test_press_modifier_combo(self, d):
        interaction.press("Control+a")
        events = self._sent_events(d)
        types = [e["type"] for e in events]
        assert types == ["rawKeyDown", "rawKeyDown", "keyUp", "keyUp"]
        assert events[0]["key"] == "Control"
        assert events[1]["key"] == "a"
        assert events[1]["modifiers"] == 2  # Control held while "a" goes down

    def test_press_unknown_key_raises(self, d):
        with pytest.raises(ValueError, match="Unknown key"):
            interaction.press("Nonexistent")


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


class TestScrollUntilCount:
    def test_returns_once_target_reached(self, d):
        d.find_elements.side_effect = [[1], [1, 2], [1, 2, 3]]
        result = interaction.scroll_until_count("#item", 3)
        assert result == 3
        assert d.scroll_down.call_count == 2

    def test_resolves_ref_selector(self, d):
        d.find_elements.return_value = [1, 2, 3]
        interaction.scroll_until_count("@e1", 3)
        d.find_elements.assert_called_with('[data-llmb-ref="e1"]')

    def test_stops_when_growth_stalls(self, d):
        d.find_elements.side_effect = [[1], [1, 2], [1, 2]]
        result = interaction.scroll_until_count("#item", 10)
        assert result == 2
        assert d.scroll_down.call_count == 2

    def test_stops_at_timeout(self, d, monkeypatch):
        times = iter([0, 0, 100])  # deadline check trips on 3rd read
        monkeypatch.setattr(interaction.time, "monotonic", lambda: next(times))
        d.find_elements.return_value = [1]
        result = interaction.scroll_until_count("#item", 10, timeout=1)
        assert result == 1


class TestScrollUntilStable:
    def test_returns_once_height_stops_growing(self, d):
        d.evaluate.side_effect = [100, 200, 300, 300, 300]
        result = interaction.scroll_until_stable()
        assert result == 300
        assert d.scroll_down.call_count == 4

    def test_stops_when_growth_stalls_immediately(self, d):
        d.evaluate.side_effect = [100, 100, 100]
        result = interaction.scroll_until_stable()
        assert result == 100
        assert d.scroll_down.call_count == 2

    def test_stops_at_timeout(self, d, monkeypatch):
        times = iter([0, 0, 100])  # deadline check trips on 3rd read
        monkeypatch.setattr(interaction.time, "monotonic", lambda: next(times))
        d.evaluate.return_value = 100
        result = interaction.scroll_until_stable(timeout=1)
        assert result == 100


def test_scroll_into_view(d):
    interaction.scroll_into_view("#a")
    d.scroll_into_view.assert_called_once_with("#a")


def test_scroll_to_top(d):
    interaction.scroll_to_top()
    d.scroll_to_top.assert_called_once()


def test_scroll_to_bottom(d):
    interaction.scroll_to_bottom()
    d.scroll_to_bottom.assert_called_once()
