"""Snapshot & @ref system.

Fetches the accessibility tree via raw CDP (Accessibility domain, not
wrapped by sb_cdp - see docs/snapshot-and-refs.md for how this was
verified against the installed seleniumbase package), then tags each
included element in the live DOM with a `data-llmb-ref="eN"`
attribute. Every other selector-taking command in :mod:`llm_browser.browser`
then resolves `@eN` to `[data-llmb-ref="eN"]` via
``core.resolve_selector()`` and flows through the normal sb_cdp
methods unchanged.
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass, field
from typing import Any

import mycdp
import mycdp.accessibility
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import _REF_ATTR, with_driver

_INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "option",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "slider",
    "spinbutton",
    "switch",
    "tab",
}

_SKIP_WHEN_COMPACT = {"generic", "none"}

# Roles that never carry information worth a line of their own, dropped
# unconditionally (not just under -c/--compact): RootWebArea is the
# #document wrapper every tree has at its root, and InlineTextBox is
# Chrome's internal echo of its parent StaticText's name - both are
# 100% redundant with content shown elsewhere.
_ALWAYS_SKIP_ROLES = {"RootWebArea", "InlineTextBox"}

# ARIA state properties surfaced as trailing [key=value] attrs in the
# rendered tree, in the order they're printed when more than one is
# present on a node. Kept short and Playwright-ARIA-snapshot-like on
# purpose - relationship/hidden-reason properties (activedescendant,
# controls, ariaHiddenElement, ...) are deliberately excluded to keep
# output compact.
_STATE_PROPS_ORDER = [
    "expanded",
    "checked",
    "pressed",
    "selected",
    "disabled",
    "required",
    "readonly",
    "level",
]

# Of the above, these reflect a widget's current toggle position and
# are worth showing either way; the rest behave like HTML boolean
# attributes and are only interesting when true (e.g. `required=false`
# is the uninformative default for almost every element).
_STATE_PROPS_ALWAYS_SHOWN = {"expanded", "checked", "pressed", "selected", "level"}
_NON_ELEMENT_ROLES = {
    "StaticText",
    "InlineTextBox",
    "LineBreak",
    # RootWebArea's backendDOMNodeId is the #document node, not <html> -
    # DOM.setAttributeValue on a document node throws a CDP protocol
    # error, which the underlying connection.send() swallows by closing
    # the websocket outright (see docs/snapshot-and-refs.md).
    "RootWebArea",
}


@dataclass
class _SnapshotNode:
    ax_id: str
    role: str
    name: str
    backend_dom_node_id: Any
    ignored: bool = False
    child_ids: list[str] = field(default_factory=list)
    ref: str | None = None
    properties: list[tuple[str, str]] = field(default_factory=list)


def _cdp_send(driver: CDPMethods, command: Any) -> Any:
    return driver.loop.run_until_complete(driver.page.send(command))


def _ax_value_str(value: Any) -> str:
    if value is None or value.value is None:
        return ""
    v = value.value
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _extract_properties(props: Any) -> list[tuple[str, str]]:
    """Pull the allowlisted ARIA state props off a raw AXNode.properties
    list, in `_STATE_PROPS_ORDER` order (not the order CDP returns them
    in)."""
    if not props:
        return []
    by_name = {}
    for p in props:
        name = p.name.value if hasattr(p.name, "value") else str(p.name)
        by_name[name] = _ax_value_str(p.value)
    result = []
    for name in _STATE_PROPS_ORDER:
        if name not in by_name:
            continue
        value = by_name[name]
        if name not in _STATE_PROPS_ALWAYS_SHOWN and value == "false":
            continue
        result.append((name, value))
    return result


def _build_index(nodes: list) -> dict[str, _SnapshotNode]:
    # Keep ignored nodes in the index (just marked `ignored`) rather than
    # dropping them outright: a node CDP marks ignored can still be the
    # parent of perfectly meaningful children (e.g. a wrapper <div> with
    # no role, containing the actual heading/paragraph/link nodes), and
    # dropping it here would sever the tree above those children. Ignored
    # nodes are always excluded from the *rendered* output in
    # `_filter_and_level` instead, which also re-attaches their children
    # to the nearest kept ancestor.
    index: dict[str, _SnapshotNode] = {}
    for n in nodes:
        index[str(n.node_id)] = _SnapshotNode(
            ax_id=str(n.node_id),
            role=_ax_value_str(n.role) or "generic",
            name=_ax_value_str(n.name),
            backend_dom_node_id=n.backend_dom_node_id,
            ignored=n.ignored,
            child_ids=[str(c) for c in (n.child_ids or [])],
            properties=_extract_properties(getattr(n, "properties", None)),
        )
    return index


def _find_root(index: dict[str, _SnapshotNode]) -> str | None:
    child_ids = {cid for node in index.values() for cid in node.child_ids}
    for ax_id in index:
        if ax_id not in child_ids:
            return ax_id
    return next(iter(index), None)


def _find_ax_id_for_selector(
    driver: CDPMethods, index: dict[str, _SnapshotNode], selector: str
) -> str:
    doc = _cdp_send(driver, mycdp.dom.get_document())
    node_id = _cdp_send(driver, mycdp.dom.query_selector(doc.node_id, selector))
    if not node_id:
        raise ValueError(f"No element matches selector: {selector!r}")
    described = _cdp_send(driver, mycdp.dom.describe_node(node_id=node_id))
    target_backend_id = int(described.backend_node_id)
    for ax_id, node in index.items():
        if (
            node.backend_dom_node_id is not None
            and int(node.backend_dom_node_id) == target_backend_id
        ):
            return ax_id
    raise ValueError(f"No accessibility node found for selector: {selector!r}")


def _iter_nodes(
    index: dict[str, _SnapshotNode],
    ax_id: str | None,
    raw_depth: int,
    depth_limit: int | None,
):
    """DFS over the raw AX tree, yielding (raw_depth, node) pairs."""
    if ax_id is None or ax_id not in index:
        return
    if depth_limit is not None and raw_depth > depth_limit:
        return
    node = index[ax_id]
    yield raw_depth, node
    for child_id in node.child_ids:
        yield from _iter_nodes(index, child_id, raw_depth + 1, depth_limit)


def _filter_and_level(pairs, interactive: bool, compact: bool):
    """Apply -i/-c filters plus the unconditional always-on ones
    (RootWebArea/InlineTextBox, unnamed generic/none wrapper collapsing
    for 0-or-1 children), re-leveling so dropped nodes' children attach
    to the nearest kept ancestor (no gaps in the indentation)."""
    kept = []
    # Stack of (raw_depth, assigned_level) for the current ancestor chain.
    stack: list[tuple[int, int]] = []
    for raw_depth, node in pairs:
        while stack and stack[-1][0] >= raw_depth:
            stack.pop()
        parent_level = stack[-1][1] if stack else -1
        include = not node.ignored
        if node.role in _ALWAYS_SKIP_ROLES:
            include = False
        # An unnamed generic/none node that doesn't branch (0 or 1
        # children) carries no information of its own: with 1 child
        # it's a no-op wrapper div, with 0 children it's an empty/
        # decorative leaf (e.g. an icon <svg> with nothing accessible
        # inside). Nodes with 2+ children are real grouping and kept.
        if (
            not node.name
            and node.role in {"generic", "none"}
            and len(node.child_ids) <= 1
        ):
            include = False
        if interactive and node.role not in _INTERACTIVE_ROLES:
            include = False
        if compact and not node.name and node.role in _SKIP_WHEN_COMPACT:
            include = False
        if include:
            level = parent_level + 1
            kept.append((level, node))
            stack.append((raw_depth, level))
        else:
            stack.append((raw_depth, parent_level))
    return kept


# Roles whose accessible `name` is computed from their full subtree text
# (ARIA "name from content"). When one of these is rendered, its
# descendants (typically StaticText echoing the same text) are skipped -
# see `_render_markdown`.
_NAME_FROM_CONTENT_ROLES = {
    "heading",
    "link",
    "listitem",
    "button",
    "tab",
    "menuitem",
    "option",
    "cell",
    "columnheader",
    "rowheader",
    "treeitem",
    "switch",
    "checkbox",
    "radio",
}


def _heading_level(node: "_SnapshotNode") -> int:
    for key, value in node.properties:
        if key == "level":
            try:
                return max(1, min(6, int(value)))
            except ValueError:
                break
    return 1


def _mark_threaded_listitems(levels) -> set[int]:
    """Indices of `listitem` nodes that have a nested `listitem` descendant
    (a reply list) - these are comment-thread-style nesting and should
    render as blockquotes rather than dash bullets. A flat, non-nested
    list of `listitem`s is left alone."""
    threaded: set[int] = set()
    for i, (level, node) in enumerate(levels):
        if node.role != "listitem":
            continue
        for child_level, child_node in levels[i + 1 :]:
            if child_level <= level:
                break
            if child_node.role == "listitem":
                threaded.add(i)
                break
    return threaded


# Link/listitem labels that only ever show up in a comment's own action
# menu (permalink/reply/save/...), never in page navigation, sidebars,
# or account widgets - see `_mark_comment_root_generics`.
_COMMENT_ACTION_LABELS = {
    "permalink",
    "reply",
    "save",
    "unsave",
    "report",
    "embed",
    "parent",
    "give award",
}

# Landmark roles that only ever appear once, at page-structure level
# (nav bar, main content region, sidebar, ...). A comment's own subtree
# never contains one of these; the page's own outermost wrapper(s)
# always do - see `_mark_comment_root_generics`.
_LANDMARK_ROLES = {
    "main",
    "banner",
    "navigation",
    "contentinfo",
    "complementary",
    "search",
    "region",
}


def _mark_comment_root_generics(levels) -> set[int]:
    """Indices of `generic` nodes that look like an individual comment's
    boundary `<div>`.

    Many forums/discussion sites (e.g. old.reddit.com) don't structure
    comment threads with nested `listitem`s at all - each comment is a
    plain `<div>` (AX role `generic`) with a `<form>` (the in-place edit
    form wrapping the comment body) and a `<ul>`/`list` of comment
    actions (permalink/reply/save/...) as direct siblings, with reply
    comments nested as further descendants. `generic` alone is far too
    common a role to key nesting off of, and even a `form`+`list` sibling
    pairing where the list's own contents are checked for comment-action
    labels can still match the page's own outermost wrapper (it has
    *some* form and *some* list among its dozens of unrelated direct
    children, and the real comment list is deep inside it) - excluding
    any generic whose subtree contains a page landmark (`main`, `banner`,
    ...) rules those out, since a comment's own subtree never contains
    one. Every match gets one blockquote level, whether or not it has
    replies, so a lone top-level comment still reads as quoted content
    distinct from surrounding page chrome."""
    roots: set[int] = set()
    for i, (level, node) in enumerate(levels):
        if node.role != "generic":
            continue
        has_form = False
        has_landmark = False
        list_idx: int | None = None
        for j in range(i + 1, len(levels)):
            child_level, child_node = levels[j]
            if child_level <= level:
                break
            if child_level == level + 1:
                if child_node.role == "form":
                    has_form = True
                elif child_node.role == "list":
                    list_idx = j
            if child_node.role in _LANDMARK_ROLES:
                has_landmark = True
        if not has_form or has_landmark or list_idx is None:
            continue
        list_level = levels[list_idx][0]
        for child_level, child_node in levels[list_idx + 1 :]:
            if child_level <= list_level:
                break
            if child_node.name.strip().lower() in _COMMENT_ACTION_LABELS:
                roots.add(i)
                break
    return roots


def _quote(text: str, depth: int) -> str:
    """Prefix every line of `text` with `depth` levels of Markdown
    blockquote marker (``> ``), so multi-line content stays validly
    quoted."""
    if depth <= 0:
        return text
    prefix = "> " * depth
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))


def _render_markdown(levels, hrefs: dict) -> str:
    """Convert the filtered/leveled AX tree straight into Markdown, e.g.:

    ``heading`` -> ``#``..``######``, ``link`` -> ``[text](href)``,
    ``listitem`` -> ``- text``, ``button`` -> ``**text**``, and plain
    ``StaticText`` -> paragraph text. Roles in `_NAME_FROM_CONTENT_ROLES`
    already carry their full text in `node.name`, so once one is emitted,
    everything below it in the tree is skipped to avoid printing the same
    text twice (once as the node's name, once via its StaticText children).

    `listitem`s that nest other `listitem`s (e.g. a comment's replies)
    render as Markdown blockquotes instead, one extra ``>`` per level of
    nesting, so reply threads stay visually readable - see
    `_mark_threaded_listitems`. Sites that structure comments as plain
    nested `<div>`s instead get the same treatment via
    `_mark_comment_root_generics`.

    Only roles with a non-empty name ever set `skip_below`: an empty
    name means nothing was emitted for that node, so there's no
    duplicate text to protect against and its children (e.g. a link
    inside an unlabeled wrapper) should still render.
    """
    threaded_indices = _mark_threaded_listitems(levels)
    comment_root_indices = _mark_comment_root_generics(levels)
    blocks: list[str] = []
    skip_below: int | None = None
    # Stack of (level, in_thread) for currently-open ancestor
    # listitem/generic nodes that contribute a blockquote level.
    thread_stack: list[tuple[int, bool]] = []
    for i, (level, node) in enumerate(levels):
        while thread_stack and thread_stack[-1][0] >= level:
            thread_stack.pop()
        quote_depth = sum(1 for _, in_thread in thread_stack if in_thread)

        if skip_below is not None:
            if level > skip_below:
                continue
            skip_below = None

        role = node.role
        name = node.name.strip()

        if role == "heading":
            if name:
                blocks.append(
                    _quote(f"{'#' * _heading_level(node)} {name}", quote_depth)
                )
                skip_below = level
        elif role == "link":
            if name:
                href = hrefs.get(node.ref) if node.ref else None
                text = f"[{name}]({href})" if href else name
                blocks.append(_quote(text, quote_depth))
                skip_below = level
        elif role == "listitem":
            is_threaded = quote_depth > 0 or i in threaded_indices
            if is_threaded:
                if name:
                    blocks.append(_quote(name, quote_depth + 1))
                if name and i not in threaded_indices:
                    # Leaf reply (no nested listitem children of its own):
                    # skip StaticText descendants just echoing this name.
                    skip_below = level
                # else: has nested replies, or nothing was emitted - don't
                # skip its children, so they still render.
            else:
                if name:
                    blocks.append(f"- {name}")
                    skip_below = level
            thread_stack.append((level, is_threaded))
        elif role == "button":
            if name:
                blocks.append(_quote(f"**{name}**", quote_depth))
                skip_below = level
        elif role in _NAME_FROM_CONTENT_ROLES:
            if name:
                blocks.append(_quote(name, quote_depth))
                skip_below = level
        elif role == "StaticText" and name:
            blocks.append(_quote(name, quote_depth))

        # `_mark_comment_root_generics` only ever marks `generic` nodes,
        # so no role check is needed here.
        if i in comment_root_indices:
            thread_stack.append((level, True))
        # else: generic/paragraph/list/table wrapper etc. with no
        # name-from-content - nothing to emit itself, children still render.

    return "\n\n".join(blocks)


def _render(levels, hrefs: dict, as_json: bool) -> str:
    items = []
    for level, node in levels:
        items.append(
            {
                "ref": f"@{node.ref}" if node.ref else None,
                "role": node.role,
                "name": node.name,
                "level": level,
                "href": hrefs.get(node.ref) if node.ref else None,
                "properties": node.properties,
            }
        )
    if as_json:
        for item in items:
            del item["properties"]
        return json_module.dumps(items, indent=2)
    # YAML-list-tree text format, e.g.:
    #   - link "About" [ref=e1]
    #     - StaticText "About"
    lines = []
    for item in items:
        indent = "  " * item["level"]
        name_part = f' "{item["name"]}"' if item["name"] else ""
        attrs = [f"{k}={v}" for k, v in item["properties"]]
        if item["ref"]:
            attrs.append(f"ref={item['ref'].lstrip('@')}")
        if item["href"]:
            attrs.append(f'href="{item["href"]}"')
        attrs_part = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f"{indent}- {item['role']}{name_part}{attrs_part}")
    return "\n".join(lines)


def snapshot(
    interactive: bool = False,
    compact: bool = False,
    depth: int | None = None,
    selector: str | None = None,
    with_urls: bool = False,
    as_json: bool = False,
    as_markdown: bool = False,
) -> str:
    if as_json and as_markdown:
        raise ValueError("as_json and as_markdown are mutually exclusive.")

    def _run(d: CDPMethods) -> str:
        # Clear stale refs from a previous snapshot before assigning new
        # ones - refs are only ever meaningful for the snapshot that
        # produced them (see docs/snapshot-and-refs.md).
        d.evaluate(
            f"document.querySelectorAll('[{_REF_ATTR}]')"
            f".forEach(el => el.removeAttribute('{_REF_ATTR}'))"
        )
        _cdp_send(d, mycdp.accessibility.enable())
        _cdp_send(d, mycdp.dom.enable())
        # DOM.getDocument() must be called at least once to initialize
        # CDP's DOM node tracking - without it, backend node ids from the
        # accessibility tree can't be resolved (pushNodesByBackendIdsToFrontend
        # silently comes back empty/None otherwise).
        _cdp_send(d, mycdp.dom.get_document())
        nodes = _cdp_send(d, mycdp.accessibility.get_full_ax_tree())
        index = _build_index(nodes)
        if not index:
            return "[]" if as_json else ""

        root_id = (
            _find_ax_id_for_selector(d, index, selector)
            if selector
            else _find_root(index)
        )
        pairs = _iter_nodes(index, root_id, 0, depth)
        levels = _filter_and_level(pairs, interactive, compact)

        ref_n = 0
        for _, node in levels:
            # Text-node AX roles (Chrome's "StaticText"/"InlineTextBox"/
            # "LineBreak" internal roles) back onto DOM Text nodes, not
            # Elements - CDP can't set an attribute on those, and
            # pushNodesByBackendIdsToFrontend itself comes back empty for
            # them. Only Element-backed nodes are taggable/actionable.
            if node.backend_dom_node_id is None or node.role in _NON_ELEMENT_ROLES:
                continue
            ref_n += 1
            node.ref = f"e{ref_n}"
            node_ids = _cdp_send(
                d,
                mycdp.dom.push_nodes_by_backend_ids_to_frontend(
                    backend_node_ids=[node.backend_dom_node_id]
                ),
            )
            if not node_ids:
                # Shouldn't happen for an Element node, but don't let one
                # unexpected miss blow up the whole snapshot.
                node.ref = None
                ref_n -= 1
                continue
            _cdp_send(
                d,
                mycdp.dom.set_attribute_value(
                    node_id=node_ids[0], name=_REF_ATTR, value=node.ref
                ),
            )

        hrefs: dict = {}
        # Markdown rendering needs hrefs to produce [text](href) links even
        # when the caller didn't ask for -u/--urls explicitly.
        if with_urls or as_markdown:
            raw = d.evaluate(
                f"JSON.stringify([...document.querySelectorAll('[{_REF_ATTR}]')]"
                f".reduce((o, el) => (o[el.getAttribute('{_REF_ATTR}')] = el.href || null, o), {{}}))"
            )
            hrefs = json_module.loads(raw) if raw else {}

        if as_markdown:
            return _render_markdown(levels, hrefs)
        return _render(levels, hrefs, as_json)

    return with_driver(_run)
