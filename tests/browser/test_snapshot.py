"""Tests for llm_browser.browser.snapshot: pure AX-tree helpers.

The CDP-talking parts of ``snapshot()`` itself are exercised via
``with_driver`` mocking; the tree-shaping helpers (index building,
filtering/re-leveling, rendering) are pure functions and tested
directly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from llm_browser.browser import snapshot as snap


def _ax_node(
    node_id,
    role,
    name,
    backend_dom_node_id,
    ignored=False,
    child_ids=None,
    properties=None,
):
    return SimpleNamespace(
        node_id=node_id,
        role=SimpleNamespace(value=role) if role is not None else None,
        name=SimpleNamespace(value=name) if name is not None else None,
        backend_dom_node_id=backend_dom_node_id,
        ignored=ignored,
        child_ids=child_ids or [],
        properties=properties,
    )


def _ax_property(name, value):
    return SimpleNamespace(
        name=SimpleNamespace(value=name), value=SimpleNamespace(value=value)
    )


class TestAxValueStr:
    def test_none_value_is_empty_string(self):
        assert snap._ax_value_str(None) == ""

    def test_value_with_none_inner_is_empty_string(self):
        assert snap._ax_value_str(SimpleNamespace(value=None)) == ""

    def test_stringifies_value(self):
        assert snap._ax_value_str(SimpleNamespace(value="hello")) == "hello"

    def test_stringifies_non_string_value(self):
        assert snap._ax_value_str(SimpleNamespace(value=42)) == "42"

    def test_lowercases_booleans(self):
        assert snap._ax_value_str(SimpleNamespace(value=True)) == "true"
        assert snap._ax_value_str(SimpleNamespace(value=False)) == "false"


class TestBuildIndex:
    def test_builds_index_keyed_by_node_id(self):
        nodes = [
            _ax_node(1, "button", "Click me", 100),
            _ax_node(2, "generic", None, 101),
        ]
        index = snap._build_index(nodes)
        assert set(index) == {"1", "2"}
        assert index["1"].role == "button"
        assert index["1"].name == "Click me"
        assert index["2"].role == "generic"
        assert index["2"].name == ""

    def test_defaults_missing_role_to_generic(self):
        nodes = [_ax_node(1, None, None, 100)]
        index = snap._build_index(nodes)
        assert index["1"].role == "generic"

    def test_keeps_ignored_nodes_flagged(self):
        nodes = [_ax_node(1, "generic", None, 100, ignored=True)]
        index = snap._build_index(nodes)
        assert index["1"].ignored is True

    def test_child_ids_stringified(self):
        nodes = [_ax_node(1, "generic", None, 100, child_ids=[2, 3])]
        index = snap._build_index(nodes)
        assert index["1"].child_ids == ["2", "3"]

    def test_properties_filtered_to_allowlist_and_ordered(self):
        nodes = [
            _ax_node(
                1,
                "button",
                "Go",
                100,
                properties=[
                    _ax_property("focusable", True),  # not allowlisted
                    _ax_property("pressed", "false"),
                    _ax_property("expanded", "true"),
                ],
            )
        ]
        index = snap._build_index(nodes)
        # Allowlist order (expanded before pressed), not CDP's order.
        assert index["1"].properties == [("expanded", "true"), ("pressed", "false")]

    def test_no_properties_is_empty_list(self):
        nodes = [_ax_node(1, "button", "Go", 100)]
        index = snap._build_index(nodes)
        assert index["1"].properties == []

    def test_always_shown_state_prop_kept_when_false(self):
        nodes = [
            _ax_node(
                1, "button", "Go", 100, properties=[_ax_property("expanded", False)]
            )
        ]
        index = snap._build_index(nodes)
        assert index["1"].properties == [("expanded", "false")]

    def test_attribute_like_state_prop_omitted_when_false(self):
        nodes = [
            _ax_node(
                1,
                "textbox",
                "Search",
                100,
                properties=[
                    _ax_property("required", False),
                    _ax_property("disabled", False),
                    _ax_property("readonly", False),
                ],
            )
        ]
        index = snap._build_index(nodes)
        assert index["1"].properties == []

    def test_attribute_like_state_prop_kept_when_true(self):
        nodes = [
            _ax_node(
                1, "textbox", "Search", 100, properties=[_ax_property("required", True)]
            )
        ]
        index = snap._build_index(nodes)
        assert index["1"].properties == [("required", "true")]


class TestFindRoot:
    def test_finds_node_with_no_parent(self):
        index = {
            "1": snap._SnapshotNode("1", "root", "", 1, child_ids=["2"]),
            "2": snap._SnapshotNode("2", "child", "", 2),
        }
        assert snap._find_root(index) == "1"

    def test_returns_none_for_empty_index(self):
        assert snap._find_root({}) is None

    def test_falls_back_to_first_when_every_node_has_a_parent(self):
        # A cycle (shouldn't happen in real AX trees, but guards against
        # an infinite/None result here).
        index = {
            "1": snap._SnapshotNode("1", "a", "", 1, child_ids=["2"]),
            "2": snap._SnapshotNode("2", "b", "", 2, child_ids=["1"]),
        }
        assert snap._find_root(index) in index


class TestIterNodes:
    def _index(self):
        return {
            "1": snap._SnapshotNode("1", "root", "", 1, child_ids=["2", "3"]),
            "2": snap._SnapshotNode("2", "child-a", "", 2, child_ids=["4"]),
            "3": snap._SnapshotNode("3", "child-b", "", 3),
            "4": snap._SnapshotNode("4", "grandchild", "", 4),
        }

    def test_dfs_order_and_depths(self):
        index = self._index()
        pairs = list(snap._iter_nodes(index, "1", 0, None))
        assert [(d, n.ax_id) for d, n in pairs] == [
            (0, "1"),
            (1, "2"),
            (2, "4"),
            (1, "3"),
        ]

    def test_none_root_yields_nothing(self):
        assert list(snap._iter_nodes(self._index(), None, 0, None)) == []

    def test_missing_root_yields_nothing(self):
        assert list(snap._iter_nodes(self._index(), "999", 0, None)) == []

    def test_depth_limit_stops_recursion(self):
        index = self._index()
        pairs = list(snap._iter_nodes(index, "1", 0, 1))
        assert [(d, n.ax_id) for d, n in pairs] == [(0, "1"), (1, "2"), (1, "3")]

    def test_depth_limit_zero_yields_only_root(self):
        index = self._index()
        pairs = list(snap._iter_nodes(index, "1", 0, 0))
        assert [(d, n.ax_id) for d, n in pairs] == [(0, "1")]


class TestFilterAndLevel:
    def test_no_filters_assigns_sequential_levels(self):
        pairs = [
            (0, snap._SnapshotNode("1", "root", "", 1)),
            (1, snap._SnapshotNode("2", "child", "", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [(level, n.ax_id) for level, n in kept] == [(0, "1"), (1, "2")]

    def test_ignored_nodes_are_dropped_but_children_reattach(self):
        pairs = [
            (0, snap._SnapshotNode("1", "root", "", 1)),
            (1, snap._SnapshotNode("2", "generic", "", 2, ignored=True)),
            (2, snap._SnapshotNode("3", "button", "Go", 3)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        # Node 2 (ignored) is dropped; node 3 attaches directly under node 1.
        assert [(level, n.ax_id) for level, n in kept] == [(0, "1"), (1, "3")]

    def test_interactive_filter_keeps_only_interactive_roles(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "", 1)),
            (1, snap._SnapshotNode("2", "button", "Go", 2)),
            (1, snap._SnapshotNode("3", "paragraph", "text", 3)),
        ]
        kept = snap._filter_and_level(pairs, interactive=True, compact=False)
        assert [n.ax_id for _, n in kept] == ["2"]

    def test_compact_drops_unnamed_structural_nodes(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "", 1)),
            (1, snap._SnapshotNode("2", "generic", "", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=True)
        assert kept == []

    def test_compact_keeps_named_generic_nodes(self):
        pairs = [(0, snap._SnapshotNode("1", "generic", "Label", 1))]
        kept = snap._filter_and_level(pairs, interactive=False, compact=True)
        assert [n.ax_id for _, n in kept] == ["1"]

    def test_root_web_area_always_dropped_child_reattaches(self):
        pairs = [
            (0, snap._SnapshotNode("1", "RootWebArea", "Page", 1, child_ids=["2"])),
            (1, snap._SnapshotNode("2", "generic", "Body", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [(level, n.ax_id) for level, n in kept] == [(0, "2")]

    def test_inline_text_box_always_dropped_even_when_named(self):
        pairs = [
            (0, snap._SnapshotNode("1", "StaticText", "Hi", 1, child_ids=["2"])),
            (1, snap._SnapshotNode("2", "InlineTextBox", "Hi", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [n.ax_id for _, n in kept] == ["1"]

    def test_single_child_unnamed_wrapper_collapses(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "", 1, child_ids=["2"])),
            (1, snap._SnapshotNode("2", "button", "Go", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [(level, n.ax_id) for level, n in kept] == [(0, "2")]

    def test_multi_child_unnamed_wrapper_kept(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "", 1, child_ids=["2", "3"])),
            (1, snap._SnapshotNode("2", "link", "A", 2)),
            (1, snap._SnapshotNode("3", "link", "B", 3)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [(level, n.ax_id) for level, n in kept] == [(0, "1"), (1, "2"), (1, "3")]

    def test_empty_unnamed_leaf_generic_dropped(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "", 1, child_ids=["2"])),
            (1, snap._SnapshotNode("2", "generic", "", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert kept == []

    def test_empty_named_leaf_generic_kept(self):
        pairs = [(0, snap._SnapshotNode("1", "generic", "Icon", 1))]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [n.ax_id for _, n in kept] == ["1"]

    def test_single_child_named_wrapper_kept(self):
        pairs = [
            (0, snap._SnapshotNode("1", "generic", "Label", 1, child_ids=["2"])),
            (1, snap._SnapshotNode("2", "button", "Go", 2)),
        ]
        kept = snap._filter_and_level(pairs, interactive=False, compact=False)
        assert [n.ax_id for _, n in kept] == ["1", "2"]


class TestRender:
    def test_text_rendering_includes_ref_role_name_href(self):
        node = snap._SnapshotNode("1", "link", "Home", 1, ref="e1")
        out = snap._render([(0, node)], {"e1": "https://example.com"}, as_json=False)
        assert out == '- link "Home" [ref=e1, href="https://example.com"]'

    def test_text_rendering_indents_by_level(self):
        node = snap._SnapshotNode("2", "button", "Go", 2, ref="e2")
        out = snap._render([(2, node)], {}, as_json=False)
        assert out.startswith("    - ")

    def test_text_rendering_omits_missing_parts(self):
        node = snap._SnapshotNode("1", "generic", "", 1)
        out = snap._render([(0, node)], {}, as_json=False)
        assert out == "- generic"

    def test_text_rendering_includes_state_properties_before_ref(self):
        node = snap._SnapshotNode(
            "1",
            "button",
            "Google apps",
            1,
            ref="e19",
            properties=[("expanded", "false")],
        )
        out = snap._render([(0, node)], {}, as_json=False)
        assert out == '- button "Google apps" [expanded=false, ref=e19]'

    def test_json_rendering(self):
        node = snap._SnapshotNode("1", "button", "Go", 1, ref="e1")
        out = snap._render([(0, node)], {"e1": None}, as_json=True)
        data = json.loads(out)
        assert data == [
            {"ref": "@e1", "role": "button", "name": "Go", "level": 0, "href": None}
        ]

    def test_json_rendering_ref_none_when_untagged(self):
        node = snap._SnapshotNode("1", "generic", "", 1)
        out = snap._render([(0, node)], {}, as_json=True)
        data = json.loads(out)
        assert data[0]["ref"] is None


class TestFindAxIdForSelector:
    def test_raises_when_selector_matches_nothing(self, monkeypatch):
        driver = MagicMock()
        calls = {"n": 0}

        def fake_send(d, cmd):
            calls["n"] += 1
            # First call is DOM.getDocument(); second is the
            # querySelector() whose result is checked for truthiness.
            return SimpleNamespace(node_id=1) if calls["n"] == 1 else None

        monkeypatch.setattr(snap, "_cdp_send", fake_send)
        import pytest

        with pytest.raises(ValueError, match="No element matches selector"):
            snap._find_ax_id_for_selector(driver, {}, "#missing")

    def test_finds_matching_ax_node_by_backend_id(self, monkeypatch):
        driver = MagicMock()
        calls = {"n": 0}

        def fake_send(d, cmd):
            calls["n"] += 1
            if calls["n"] == 1:
                return SimpleNamespace(node_id=1)
            if calls["n"] == 2:
                return SimpleNamespace(node_id=5)
            return SimpleNamespace(backend_node_id=42)

        monkeypatch.setattr(snap, "_cdp_send", fake_send)
        index = {
            "a": snap._SnapshotNode("a", "generic", "", None),
            "b": snap._SnapshotNode("b", "button", "Go", 42),
        }
        result = snap._find_ax_id_for_selector(driver, index, "#go")
        assert result == "b"

    def test_raises_when_no_ax_node_matches_backend_id(self, monkeypatch):
        def fake_send(d, cmd):
            if not hasattr(fake_send, "_step"):
                fake_send._step = 0
            fake_send._step += 1
            if fake_send._step == 1:
                return SimpleNamespace(node_id=1)
            if fake_send._step == 2:
                return SimpleNamespace(node_id=5)
            return SimpleNamespace(backend_node_id=999)

        monkeypatch.setattr(snap, "_cdp_send", fake_send)
        index = {"a": snap._SnapshotNode("a", "generic", "", 1)}
        import pytest

        with pytest.raises(ValueError, match="No accessibility node found"):
            snap._find_ax_id_for_selector(MagicMock(), index, "#go")
