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


class TestHeadingLevel:
    def test_defaults_to_1_when_no_level_property(self):
        node = snap._SnapshotNode("1", "heading", "Title", 1)
        assert snap._heading_level(node) == 1

    def test_reads_level_property(self):
        node = snap._SnapshotNode(
            "1", "heading", "Title", 1, properties=[("level", "3")]
        )
        assert snap._heading_level(node) == 3

    def test_clamps_to_1_through_6(self):
        node = snap._SnapshotNode(
            "1", "heading", "Title", 1, properties=[("level", "9")]
        )
        assert snap._heading_level(node) == 6


class TestRenderMarkdown:
    def test_heading_renders_with_hashes(self):
        node = snap._SnapshotNode(
            "1", "heading", "Title", 1, properties=[("level", "2")]
        )
        out = snap._render_markdown([(0, node)], {})
        assert out == "## Title"

    def test_link_renders_with_href(self):
        node = snap._SnapshotNode("1", "link", "Home", 1, ref="e1")
        out = snap._render_markdown([(0, node)], {"e1": "https://example.com"})
        assert out == "[Home](https://example.com)"

    def test_link_without_href_renders_as_plain_text(self):
        node = snap._SnapshotNode("1", "link", "Home", 1, ref="e1")
        out = snap._render_markdown([(0, node)], {})
        assert out == "Home"

    def test_listitem_renders_with_dash(self):
        node = snap._SnapshotNode("1", "listitem", "First", 1)
        out = snap._render_markdown([(0, node)], {})
        assert out == "- First"

    def test_button_renders_bold(self):
        node = snap._SnapshotNode("1", "button", "Submit", 1)
        out = snap._render_markdown([(0, node)], {})
        assert out == "**Submit**"

    def test_static_text_renders_as_paragraph(self):
        node = snap._SnapshotNode("1", "StaticText", "Some text.", 1)
        out = snap._render_markdown([(0, node)], {})
        assert out == "Some text."

    def test_generic_wrapper_emits_nothing_itself(self):
        node = snap._SnapshotNode("1", "generic", "", 1)
        out = snap._render_markdown([(0, node)], {})
        assert out == ""

    def test_static_text_child_of_link_is_not_duplicated(self):
        link = snap._SnapshotNode("1", "link", "About", 1, ref="e1")
        text = snap._SnapshotNode("2", "StaticText", "About", 2)
        out = snap._render_markdown([(0, link), (1, text)], {"e1": "/about"})
        assert out == "[About](/about)"

    def test_static_text_sibling_after_link_subtree_is_kept(self):
        link = snap._SnapshotNode("1", "link", "About", 1, ref="e1")
        link_text = snap._SnapshotNode("2", "StaticText", "About", 2)
        other = snap._SnapshotNode("3", "StaticText", "More text.", 3)
        out = snap._render_markdown(
            [(0, link), (1, link_text), (0, other)], {"e1": "/about"}
        )
        assert out == "[About](/about)\n\nMore text."

    def test_multiple_blocks_joined_by_blank_line(self):
        heading = snap._SnapshotNode(
            "1", "heading", "Title", 1, properties=[("level", "1")]
        )
        para = snap._SnapshotNode("2", "StaticText", "Body text.", 2)
        out = snap._render_markdown([(0, heading), (0, para)], {})
        assert out == "# Title\n\nBody text."

    def test_flat_listitems_without_nesting_still_use_dash(self):
        a = snap._SnapshotNode("1", "listitem", "First", 1)
        b = snap._SnapshotNode("2", "listitem", "Second", 2)
        out = snap._render_markdown([(0, a), (0, b)], {})
        assert out == "- First\n\n- Second"

    def test_nested_listitem_renders_as_blockquote(self):
        top = snap._SnapshotNode("1", "listitem", "Top comment", 1)
        reply = snap._SnapshotNode("2", "listitem", "Reply", 2)
        out = snap._render_markdown([(0, top), (1, reply)], {})
        assert out == "> Top comment\n\n> > Reply"

    def test_three_levels_of_nested_listitems(self):
        top = snap._SnapshotNode("1", "listitem", "Top", 1)
        mid = snap._SnapshotNode("2", "listitem", "Mid", 2)
        leaf = snap._SnapshotNode("3", "listitem", "Leaf", 3)
        out = snap._render_markdown([(0, top), (1, mid), (2, leaf)], {})
        assert out == "> Top\n\n> > Mid\n\n> > > Leaf"

    def test_static_text_body_inside_threaded_listitem_is_quoted(self):
        top = snap._SnapshotNode("1", "listitem", "Top comment", 1)
        body = snap._SnapshotNode("2", "StaticText", "Body text.", 2)
        reply = snap._SnapshotNode("3", "listitem", "Reply", 3)
        out = snap._render_markdown([(0, top), (1, body), (1, reply)], {})
        assert out == "> Top comment\n\n> Body text.\n\n> > Reply"

    def test_sibling_top_level_threads_each_start_at_depth_one(self):
        top1 = snap._SnapshotNode("1", "listitem", "Thread 1", 1)
        reply1 = snap._SnapshotNode("2", "listitem", "Reply 1", 2)
        top2 = snap._SnapshotNode("3", "listitem", "Thread 2", 3)
        reply2 = snap._SnapshotNode("4", "listitem", "Reply 2", 4)
        out = snap._render_markdown(
            [(0, top1), (1, reply1), (0, top2), (1, reply2)], {}
        )
        assert out == "> Thread 1\n\n> > Reply 1\n\n> Thread 2\n\n> > Reply 2"

    def test_reddit_style_div_comment_renders_as_blockquote(self):
        # Sites like old.reddit.com don't nest `listitem`s for comments at
        # all - each comment is an unnamed `generic` <div> with a `form`
        # (body text) and a `list` of action links (permalink/reply/...)
        # as direct siblings.
        comment = snap._SnapshotNode("1", "generic", "", 1)
        form = snap._SnapshotNode("2", "form", "", 2)
        body = snap._SnapshotNode("3", "StaticText", "Nice post.", 3)
        actions = snap._SnapshotNode("4", "list", "", 4)
        action_item = snap._SnapshotNode("5", "listitem", "", 5)
        permalink = snap._SnapshotNode("6", "link", "permalink", 6)
        levels = [
            (0, comment),
            (1, form),
            (2, body),
            (1, actions),
            (2, action_item),
            (3, permalink),
        ]
        out = snap._render_markdown(levels, {})
        assert out == "> Nice post.\n\n> > permalink"

    def test_generic_with_landmark_descendant_is_not_a_comment_root(self):
        # A `form`+`list`(w/ a comment-action label) pairing alone isn't
        # enough - the page's own outermost wrapper can coincidentally
        # have both among its many unrelated children. A `main`/`banner`/
        # etc. landmark descendant means it's page structure, not a
        # comment, and should be left unquoted.
        wrapper = snap._SnapshotNode("1", "generic", "", 1)
        form = snap._SnapshotNode("2", "form", "", 2)
        actions = snap._SnapshotNode("3", "list", "", 3)
        action_item = snap._SnapshotNode("4", "listitem", "", 4)
        reply = snap._SnapshotNode("5", "link", "reply", 5)
        main = snap._SnapshotNode("6", "main", "", 6)
        body = snap._SnapshotNode("7", "StaticText", "Page content.", 7)
        levels = [
            (0, wrapper),
            (1, form),
            (1, actions),
            (2, action_item),
            (3, reply),
            (1, main),
            (2, body),
        ]
        out = snap._render_markdown(levels, {})
        assert out == "reply\n\nPage content."

    def test_empty_named_listitem_does_not_swallow_child_link(self):
        # A `listitem` with no accessible name (common for a wrapper
        # around a single interactive child, e.g. an action-menu item)
        # has nothing of its own to duplicate, so its child must still
        # render instead of being dropped by the old-content skip.
        item = snap._SnapshotNode("1", "listitem", "", 1)
        link = snap._SnapshotNode("2", "link", "reply", 2)
        out = snap._render_markdown([(0, item), (1, link)], {})
        assert out == "reply"


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
