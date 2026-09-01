"""CLI-level tests: Typer arg parsing wiring through to the browser layer.

Each test invokes the real Typer app via ``CliRunner`` and monkeypatches
the underlying ``llm_browser.browser.*`` function the command delegates
to, so these exercise argument parsing/formatting without touching a
real browser.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from llm_browser.browser import (
    captcha,
    capture,
    core,
    fetch,
    gui,
    info,
    interaction,
    misc,
    navigation,
    state,
    storage,
    tabs,
)
from llm_browser.browser import evaluate as evaluate_mod
from llm_browser.browser import extract as extract_mod
from llm_browser.browser import search as search_mod
from llm_browser.browser import snapshot as snapshot_mod
from llm_browser.browser import wait as wait_mod
from llm_browser.cli import app

runner = CliRunner()


def test_app_help_lists_top_level_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "open" in result.output
    assert "snapshot" in result.output


class TestNavigation:
    def test_open(self, monkeypatch):
        open_url = MagicMock()
        monkeypatch.setattr(core, "open_url", open_url)
        result = runner.invoke(app, ["open", "https://example.com", "--headless"])
        assert result.exit_code == 0
        open_url.assert_called_once_with("https://example.com", headless=True)

    def test_close_when_session_running(self, monkeypatch):
        monkeypatch.setattr(core, "close_session", lambda: True)
        result = runner.invoke(app, ["close"])
        assert result.exit_code == 0
        assert "Session closed." in result.output

    def test_close_when_no_session(self, monkeypatch):
        monkeypatch.setattr(core, "close_session", lambda: False)
        result = runner.invoke(app, ["close"])
        assert "No running session." in result.output

    def test_back(self, monkeypatch):
        go_back = MagicMock()
        monkeypatch.setattr(navigation, "go_back", go_back)
        result = runner.invoke(app, ["back"])
        assert result.exit_code == 0
        go_back.assert_called_once()

    def test_reload_ignore_cache(self, monkeypatch):
        reload_page = MagicMock()
        monkeypatch.setattr(navigation, "reload_page", reload_page)
        result = runner.invoke(app, ["reload", "--ignore-cache"])
        assert result.exit_code == 0
        reload_page.assert_called_once_with(ignore_cache=True)


class TestInteraction:
    def test_click_by_selector(self, monkeypatch):
        click = MagicMock()
        monkeypatch.setattr(interaction, "click", click)
        result = runner.invoke(app, ["click", "#submit"])
        assert result.exit_code == 0
        click.assert_called_once_with(selector="#submit", text=None)

    def test_click_by_text(self, monkeypatch):
        click = MagicMock()
        monkeypatch.setattr(interaction, "click", click)
        result = runner.invoke(app, ["click", "--text", "Submit"])
        assert result.exit_code == 0
        click.assert_called_once_with(selector=None, text="Submit")

    def test_click_gui_requires_selector(self, monkeypatch):
        result = runner.invoke(app, ["click", "--gui"])
        assert result.exit_code != 0

    def test_click_gui_routes_to_gui_module(self, monkeypatch):
        gui_click = MagicMock()
        monkeypatch.setattr(gui, "gui_click", gui_click)
        result = runner.invoke(app, ["click", "#a", "--gui"])
        assert result.exit_code == 0
        gui_click.assert_called_once_with("#a")

    def test_type_command(self, monkeypatch):
        type_text = MagicMock()
        monkeypatch.setattr(interaction, "type_text", type_text)
        result = runner.invoke(app, ["type", "#a", "hello"])
        assert result.exit_code == 0
        type_text.assert_called_once_with("#a", "hello")

    def test_fill(self, monkeypatch):
        fill = MagicMock()
        monkeypatch.setattr(interaction, "fill", fill)
        result = runner.invoke(app, ["fill", "#a", "hello"])
        assert result.exit_code == 0
        fill.assert_called_once_with("#a", "hello")

    def test_hover_gui_not_supported(self):
        result = runner.invoke(app, ["hover", "#a", "--gui"])
        assert result.exit_code != 0
        assert "gui-hover-click" in result.output

    def test_select_multiple_values(self, monkeypatch):
        select_option = MagicMock()
        monkeypatch.setattr(interaction, "select_option", select_option)
        result = runner.invoke(app, ["select", "#a", "x", "y"])
        assert result.exit_code == 0
        select_option.assert_called_once_with("#a", ["x", "y"])

    def test_scroll_top_routes_to_scroll_to_top(self, monkeypatch):
        scroll_to_top = MagicMock()
        monkeypatch.setattr(interaction, "scroll_to_top", scroll_to_top)
        result = runner.invoke(app, ["scroll", "top"])
        assert result.exit_code == 0
        scroll_to_top.assert_called_once()

    def test_scroll_bottom_routes_to_scroll_to_bottom(self, monkeypatch):
        scroll_to_bottom = MagicMock()
        monkeypatch.setattr(interaction, "scroll_to_bottom", scroll_to_bottom)
        result = runner.invoke(app, ["scroll", "bottom"])
        assert result.exit_code == 0
        scroll_to_bottom.assert_called_once()

    def test_scroll_direction_and_px(self, monkeypatch):
        scroll = MagicMock()
        monkeypatch.setattr(interaction, "scroll", scroll)
        result = runner.invoke(app, ["scroll", "down", "100"])
        assert result.exit_code == 0
        scroll.assert_called_once_with("down", 100)

    def test_scroll_until_count(self, monkeypatch):
        scroll_until_count = MagicMock(return_value=12)
        monkeypatch.setattr(interaction, "scroll_until_count", scroll_until_count)
        result = runner.invoke(
            app,
            [
                "scroll",
                "down",
                "--until-count",
                "10",
                "--selector",
                ".item",
                "--timeout",
                "5",
            ],
        )
        assert result.exit_code == 0
        assert result.output.strip() == "12"
        scroll_until_count.assert_called_once_with(".item", 10, px=300, timeout=5.0)

    def test_scroll_until_count_requires_selector(self, monkeypatch):
        result = runner.invoke(app, ["scroll", "down", "--until-count", "10"])
        assert result.exit_code != 0


class TestWait:
    def test_wait_forwards_all_options(self, monkeypatch):
        wait_for = MagicMock()
        monkeypatch.setattr(wait_mod, "wait_for", wait_for)
        result = runner.invoke(
            app, ["wait", "#a", "--text", "Loaded", "--timeout", "5"]
        )
        assert result.exit_code == 0
        wait_for.assert_called_once_with(
            selector="#a", ms=None, text="Loaded", url=None, js_fn=None, timeout=5.0
        )


class TestGetInfo:
    def test_get_text(self, monkeypatch):
        monkeypatch.setattr(info, "get_text", lambda sel: "hello")
        result = runner.invoke(app, ["get", "text", "#a"])
        assert result.exit_code == 0
        assert result.output.strip() == "hello"

    def test_get_count_prints_json_number(self, monkeypatch):
        monkeypatch.setattr(info, "get_count", lambda sel: 3)
        result = runner.invoke(app, ["get", "count", "#a"])
        assert result.exit_code == 0
        assert result.output.strip() == "3"

    def test_get_box_prints_json_dict(self, monkeypatch):
        monkeypatch.setattr(info, "get_box", lambda sel: {"x": 1, "y": 2})
        result = runner.invoke(app, ["get", "box", "#a"])
        assert result.exit_code == 0
        assert json.loads(result.output) == {"x": 1, "y": 2}

    def test_get_styles_with_prop(self, monkeypatch):
        captured = {}

        def fake_get_styles(selector, prop=None):
            captured["args"] = (selector, prop)
            return "red"

        monkeypatch.setattr(info, "get_styles", fake_get_styles)
        result = runner.invoke(app, ["get", "styles", "#a", "--prop", "color"])
        assert result.exit_code == 0
        assert captured["args"] == ("#a", "color")


class TestIs:
    def test_is_visible_true(self, monkeypatch):
        monkeypatch.setattr(state, "is_visible", lambda sel: True)
        result = runner.invoke(app, ["is", "visible", "#a"])
        assert result.exit_code == 0
        assert result.output.strip() == "true"

    def test_is_online(self, monkeypatch):
        monkeypatch.setattr(misc, "is_online", lambda: False)
        result = runner.invoke(app, ["is", "online"])
        assert result.exit_code == 0
        assert result.output.strip() == "false"


class TestCookiesAndStorage:
    def test_cookies_get(self, monkeypatch):
        monkeypatch.setattr(storage, "cookies_get", lambda: [{"name": "a"}])
        result = runner.invoke(app, ["cookies", "get"])
        assert result.exit_code == 0
        assert json.loads(result.output) == [{"name": "a"}]

    def test_cookies_set(self, monkeypatch):
        cookies_set = MagicMock()
        monkeypatch.setattr(storage, "cookies_set", cookies_set)
        result = runner.invoke(app, ["cookies", "set", "k", "v"])
        assert result.exit_code == 0
        cookies_set.assert_called_once_with("k", "v")

    def test_storage_get_with_session_flag(self, monkeypatch):
        captured = {}

        def fake_get(key=None, use_session=False):
            captured["args"] = (key, use_session)
            return "val"

        monkeypatch.setattr(storage, "storage_get", fake_get)
        result = runner.invoke(app, ["storage", "get", "k", "--session-storage"])
        assert result.exit_code == 0
        assert captured["args"] == ("k", True)


class TestTabsAndWindows:
    def test_tab_new(self, monkeypatch):
        tab_new = MagicMock()
        monkeypatch.setattr(tabs, "tab_new", tab_new)
        result = runner.invoke(app, ["tab", "new", "https://x"])
        assert result.exit_code == 0
        tab_new.assert_called_once_with("https://x")

    def test_tab_new_extract_defaults_to_markdown(self, monkeypatch):
        tab_new_extract = MagicMock(return_value="# Title")
        monkeypatch.setattr(tabs, "tab_new_extract", tab_new_extract)
        result = runner.invoke(app, ["tab", "new", "https://x", "--extract"])
        assert result.exit_code == 0
        assert result.output.strip() == "# Title"
        tab_new_extract.assert_called_once_with(
            "https://x", markdown=True, close=False
        )

    def test_tab_new_extract_text_and_close_flags(self, monkeypatch):
        tab_new_extract = MagicMock(return_value="Title")
        monkeypatch.setattr(tabs, "tab_new_extract", tab_new_extract)
        result = runner.invoke(
            app, ["tab", "new", "https://x", "--extract", "--text", "--close"]
        )
        assert result.exit_code == 0
        tab_new_extract.assert_called_once_with(
            "https://x", markdown=False, close=True
        )

    def test_tab_new_extract_without_url_errors(self, monkeypatch):
        tab_new_extract = MagicMock()
        monkeypatch.setattr(tabs, "tab_new_extract", tab_new_extract)
        result = runner.invoke(app, ["tab", "new", "--extract"])
        assert result.exit_code != 0
        tab_new_extract.assert_not_called()

    def test_tab_list(self, monkeypatch):
        monkeypatch.setattr(tabs, "tab_list", lambda: [{"index": 0}])
        result = runner.invoke(app, ["tab", "list"])
        assert result.exit_code == 0
        assert json.loads(result.output) == [{"index": 0}]

    def test_tab_switch(self, monkeypatch):
        tab_switch = MagicMock()
        monkeypatch.setattr(tabs, "tab_switch", tab_switch)
        result = runner.invoke(app, ["tab", "switch", "2"])
        assert result.exit_code == 0
        tab_switch.assert_called_once_with(2)

    def test_window_new(self, monkeypatch):
        window_new = MagicMock()
        monkeypatch.setattr(tabs, "window_new", window_new)
        result = runner.invoke(app, ["window", "new", "https://x"])
        assert result.exit_code == 0
        window_new.assert_called_once_with("https://x")


class TestSnapshot:
    def test_snapshot_passes_flags_through(self, monkeypatch):
        captured = {}

        def fake_snapshot(**kwargs):
            captured.update(kwargs)
            return "tree"

        monkeypatch.setattr(snapshot_mod, "snapshot", fake_snapshot)
        result = runner.invoke(
            app, ["snapshot", "-i", "-c", "-d", "2", "-s", "#a", "--json"]
        )
        assert result.exit_code == 0
        assert captured == {
            "interactive": True,
            "compact": True,
            "depth": 2,
            "selector": "#a",
            "with_urls": False,
            "as_json": True,
        }
        assert result.output.strip() == "tree"


class TestMisc:
    def test_read_page(self, monkeypatch):
        monkeypatch.setattr(misc, "read_page", lambda sel: "some text")
        result = runner.invoke(app, ["read"])
        assert result.exit_code == 0
        assert result.output.strip() == "some text"

    def test_read_scoped_to_selector(self, monkeypatch):
        read_page = MagicMock(return_value="scoped text")
        monkeypatch.setattr(misc, "read_page", read_page)
        result = runner.invoke(app, ["read", "#a"])
        assert result.exit_code == 0
        read_page.assert_called_once_with("#a")

    def test_read_url_fetches_instead_of_open_page(self, monkeypatch):
        fetch_url = MagicMock(return_value="fetched text")
        read_page = MagicMock()
        monkeypatch.setattr(fetch, "fetch_url", fetch_url)
        monkeypatch.setattr(misc, "read_page", read_page)
        result = runner.invoke(app, ["read", "https://example.com"])
        assert result.exit_code == 0
        assert result.output.strip() == "fetched text"
        fetch_url.assert_called_once_with("https://example.com", markdown=False)
        read_page.assert_not_called()

    def test_read_url_with_markdown_flag(self, monkeypatch):
        fetch_url = MagicMock(return_value="# fetched markdown")
        monkeypatch.setattr(fetch, "fetch_url", fetch_url)
        result = runner.invoke(app, ["read", "https://example.com", "--markdown"])
        assert result.exit_code == 0
        fetch_url.assert_called_once_with("https://example.com", markdown=True)

    def test_mfa_code(self, monkeypatch):
        monkeypatch.setattr(misc, "mfa_code", lambda key: "123456")
        result = runner.invoke(app, ["mfa-code", "SECRET"])
        assert result.exit_code == 0
        assert result.output.strip() == "123456"


class TestSearch:
    def test_search_forwards_engine_and_query(self, monkeypatch):
        search = MagicMock(return_value="snapshot output")
        monkeypatch.setattr(search_mod, "search", search)
        result = runner.invoke(app, ["search", "google", "llm browser automation"])
        assert result.exit_code == 0
        assert result.output.strip() == "snapshot output"
        search.assert_called_once_with("google", "llm browser automation")

    def test_search_unknown_engine_exits_nonzero(self, monkeypatch):
        def raise_unknown(engine, query):
            raise ValueError(f"Unknown search engine: {engine!r}.")

        monkeypatch.setattr(search_mod, "search", raise_unknown)
        result = runner.invoke(app, ["search", "altavista", "x"])
        assert result.exit_code != 0


class TestExtract:
    def test_extract_defaults_to_markdown(self, monkeypatch):
        extract_content = MagicMock(return_value="# Title")
        monkeypatch.setattr(extract_mod, "extract_content", extract_content)
        result = runner.invoke(app, ["extract"])
        assert result.exit_code == 0
        assert result.output.strip() == "# Title"
        extract_content.assert_called_once_with(markdown=True)

    def test_extract_text_flag(self, monkeypatch):
        extract_content = MagicMock(return_value="Title")
        monkeypatch.setattr(extract_mod, "extract_content", extract_content)
        result = runner.invoke(app, ["extract", "--text"])
        assert result.exit_code == 0
        extract_content.assert_called_once_with(markdown=False)


class TestCaptcha:
    def test_solve_captcha_success(self, monkeypatch):
        monkeypatch.setattr(captcha, "solve_captcha", lambda gui: True)
        result = runner.invoke(app, ["solve-captcha"])
        assert result.exit_code == 0

    def test_solve_captcha_not_detected_exits_nonzero(self, monkeypatch):
        monkeypatch.setattr(captcha, "solve_captcha", lambda gui: False)
        result = runner.invoke(app, ["solve-captcha"])
        assert result.exit_code == 1
        assert "No supported captcha detected" in result.output


class TestCapture:
    def test_screenshot(self, monkeypatch):
        monkeypatch.setattr(
            capture, "screenshot", lambda path, full_page=False: "/tmp/out.png"
        )
        result = runner.invoke(app, ["screenshot"])
        assert result.exit_code == 0
        assert result.output.strip() == "/tmp/out.png"

    def test_screenshot_full(self, monkeypatch):
        calls = {}

        def fake_screenshot(path, full_page=False):
            calls["full_page"] = full_page
            return "/tmp/out.png"

        monkeypatch.setattr(capture, "screenshot", fake_screenshot)
        result = runner.invoke(app, ["screenshot", "--full"])
        assert result.exit_code == 0
        assert calls["full_page"] is True

    def test_pdf_requires_path(self):
        result = runner.invoke(app, ["pdf"])
        assert result.exit_code != 0


class TestEvaluate:
    def test_eval_with_arg(self, monkeypatch):
        monkeypatch.setattr(evaluate_mod, "evaluate", lambda js: "result")
        result = runner.invoke(app, ["eval", "1+1"])
        assert result.exit_code == 0
        assert result.output.strip() == "result"

    def test_eval_requires_script_or_stdin(self):
        result = runner.invoke(app, ["eval"])
        assert result.exit_code != 0

    def test_eval_from_stdin(self, monkeypatch):
        monkeypatch.setattr(evaluate_mod, "evaluate", lambda js: js)
        result = runner.invoke(app, ["eval", "--stdin"], input="document.title")
        assert result.exit_code == 0
        assert result.output.strip() == "document.title"
