"""Tests for llm_browser.browser.tabs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import tabs


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(tabs, "with_driver", lambda fn: fn(driver))
    # tab_new/tab_new_extract call core.ensure_session() before attaching -
    # without this, the real one runs and spawns an actual daemon + Chrome
    # window on the test machine.
    monkeypatch.setattr(tabs.core, "ensure_session", MagicMock())
    return driver


@pytest.fixture(autouse=True)
def labels(monkeypatch):
    """In-memory stand-in for ``~/.llm-browser/labels.json``."""
    store: dict[str, str] = {}
    monkeypatch.setattr(tabs.session, "read_labels", lambda: dict(store))

    def _write(new):
        store.clear()
        store.update(new)

    monkeypatch.setattr(tabs.session, "write_labels", _write)
    return store


@pytest.fixture(autouse=True)
def active_tab(monkeypatch):
    """In-memory stand-in for ``~/.llm-browser/active_tab``."""
    box: dict[str, str] = {}
    monkeypatch.setattr(tabs.session, "read_active_tab", lambda: box.get("id"))
    monkeypatch.setattr(tabs.session, "write_active_tab", lambda tid: box.__setitem__("id", tid))
    monkeypatch.setattr(tabs.session, "clear_active_tab", lambda: box.pop("id", None))
    return box


def _tab(target_id="t0", url=None, title=None):
    return MagicMock(target=MagicMock(target_id=target_id, url=url, title=title))


def test_tab_new_with_url(d, active_tab):
    d.get_tabs.return_value = [_tab("t0")]
    tabs.tab_new("https://example.com")
    d.open_new_tab.assert_called_once_with("https://example.com")
    assert active_tab["id"] == "t0"


def test_tab_new_without_url(d):
    d.get_tabs.return_value = [_tab("t0")]
    tabs.tab_new()
    d.open_new_tab.assert_called_once_with(None)


class TestTabNewLabel:
    def test_labels_the_newest_tab(self, d, labels):
        d.get_tabs.return_value = [_tab("t0"), _tab("t1")]
        tabs.tab_new("https://example.com", label="docs")
        assert labels == {"docs": "t1"}

    def test_duplicate_label_errors(self, d, labels):
        labels["docs"] = "t0"
        with pytest.raises(ValueError, match="already in use"):
            tabs.tab_new("https://example.com", label="docs")
        d.open_new_tab.assert_not_called()


class TestTabList:
    def test_lists_tabs_with_index_url_title(self, d):
        t0 = MagicMock(target=MagicMock(target_id="t0", url="https://a", title="A"))
        t1 = MagicMock(target=MagicMock(target_id="t1", url="https://b", title="B"))
        d.get_tabs.return_value = [t0, t1]
        result = tabs.tab_list()
        assert result == [
            {
                "index": 0,
                "url": "https://a",
                "title": "A",
                "target_id": "t0",
                "label": None,
            },
            {
                "index": 1,
                "url": "https://b",
                "title": "B",
                "target_id": "t1",
                "label": None,
            },
        ]

    def test_includes_label(self, d, labels):
        labels["docs"] = "t1"
        d.get_tabs.return_value = [_tab("t0"), _tab("t1")]
        result = tabs.tab_list()
        assert result[0]["label"] is None
        assert result[1]["label"] == "docs"

    def test_missing_target_yields_none_fields(self, d):
        t0 = MagicMock(spec=[])  # no `target` attribute at all
        d.get_tabs.return_value = [t0]
        result = tabs.tab_list()
        assert result == [
            {"index": 0, "url": None, "title": None, "target_id": None, "label": None}
        ]

    def test_empty_tabs(self, d):
        d.get_tabs.return_value = []
        assert tabs.tab_list() == []


class TestTabSwitch:
    def test_switch_by_index(self, d, active_tab):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        tabs.tab_switch("1")
        d.switch_to_tab.assert_called_once_with(t1)
        assert active_tab["id"] == "t1"

    def test_switch_by_label(self, d, labels):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        labels["docs"] = "t1"
        tabs.tab_switch("docs")
        d.switch_to_tab.assert_called_once_with(t1)

    def test_unknown_ref_raises(self, d):
        d.get_tabs.return_value = [_tab("t0")]
        with pytest.raises(ValueError, match="No tab with index or label"):
            tabs.tab_switch("nope")

    def test_stale_label_is_pruned(self, d, labels):
        d.get_tabs.return_value = [_tab("t0")]
        labels["gone"] = "t99"
        with pytest.raises(ValueError, match="no longer exists"):
            tabs.tab_switch("gone")
        assert "gone" not in labels


class TestTabClose:
    def test_close_with_index_switches_first(self, d):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        tabs.tab_close("1")
        d.switch_to_tab.assert_called_once_with(t1)
        d.close_active_tab.assert_called_once()

    def test_close_without_index_closes_current(self, d):
        d.get_active_tab.return_value = _tab("t0")
        tabs.tab_close()
        d.switch_to_tab.assert_not_called()
        d.close_active_tab.assert_called_once()

    def test_close_by_label_removes_label(self, d, labels):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        labels["docs"] = "t1"
        tabs.tab_close("docs")
        d.switch_to_tab.assert_called_once_with(t1)
        assert "docs" not in labels

    def test_close_current_removes_its_label(self, d, labels):
        d.get_active_tab.return_value = _tab("t0")
        labels["docs"] = "t0"
        tabs.tab_close()
        assert "docs" not in labels

    def test_close_clears_matching_active_tab_pointer(self, d, active_tab):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        active_tab["id"] = "t1"
        tabs.tab_close("1")
        assert "id" not in active_tab

    def test_close_leaves_other_active_tab_pointer_alone(self, d, active_tab):
        t0, t1 = _tab("t0"), _tab("t1")
        d.get_tabs.return_value = [t0, t1]
        active_tab["id"] = "t0"
        tabs.tab_close("1")
        assert active_tab["id"] == "t0"


def test_window_new(d):
    tabs.window_new("https://x")
    d.open_new_window.assert_called_once_with("https://x")


class TestTabNewExtract:
    @pytest.fixture(autouse=True)
    def _extract(self, d, monkeypatch):
        # tab_new_extract calls extract.extract_content(), which attaches
        # via its own `with_driver` - point it at the same mock driver.
        monkeypatch.setattr(tabs.extract, "with_driver", lambda fn: fn(d))
        monkeypatch.setattr(
            tabs.extract.trafilatura, "extract", lambda *a, **k: "# Title\n\nBody."
        )
        tab = _tab("t0")
        d.get_tabs.return_value = [tab]
        d.get_active_tab.return_value = tab
        return d

    def test_opens_and_extracts(self, d):
        result = tabs.tab_new_extract("https://example.com")
        d.open_new_tab.assert_called_once_with("https://example.com")
        assert result == "# Title\n\nBody."

    def test_does_not_close_by_default(self, d):
        tabs.tab_new_extract("https://example.com")
        d.close_active_tab.assert_not_called()

    def test_close_true_closes_after_extracting(self, d):
        tabs.tab_new_extract("https://example.com", close=True)
        d.close_active_tab.assert_called_once()

    def test_snapshot_true_uses_snapshot_markdown_instead_of_extract(
        self, d, monkeypatch
    ):
        fake_snapshot = MagicMock(return_value="# Snapshot Title")
        monkeypatch.setattr(tabs.snapshot_, "snapshot", fake_snapshot)
        extract_content = MagicMock()
        monkeypatch.setattr(tabs.extract, "extract_content", extract_content)

        result = tabs.tab_new_extract("https://example.com", snapshot=True)

        fake_snapshot.assert_called_once_with(
            compact=True, with_urls=True, as_markdown=True
        )
        extract_content.assert_not_called()
        assert result == "# Snapshot Title"

    def test_until_stable_scrolls_before_extracting(self, d, monkeypatch):
        scroll_until_stable = MagicMock(return_value=1234)
        monkeypatch.setattr(tabs.interaction, "scroll_until_stable", scroll_until_stable)

        result = tabs.tab_new_extract(
            "https://example.com",
            until_stable=True,
            timeout=15.0,
            stable_rounds=3,
        )

        scroll_until_stable.assert_called_once_with(px=2000, timeout=15.0, stable_rounds=3)
        assert result == "# Title\n\nBody."

    def test_until_stable_false_does_not_scroll(self, d, monkeypatch):
        scroll_until_stable = MagicMock()
        monkeypatch.setattr(tabs.interaction, "scroll_until_stable", scroll_until_stable)
        tabs.tab_new_extract("https://example.com")
        scroll_until_stable.assert_not_called()
