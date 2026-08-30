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

_SKIP_WHEN_COMPACT = {"generic", "none", "InlineTextBox"}
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


def _cdp_send(driver: CDPMethods, command: Any) -> Any:
    return driver.loop.run_until_complete(driver.page.send(command))


def _ax_value_str(value: Any) -> str:
    if value is None or value.value is None:
        return ""
    return str(value.value)


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
    """Apply -i/-c filters, re-leveling so dropped nodes' children
    attach to the nearest kept ancestor (no gaps in the indentation)."""
    kept = []
    # Stack of (raw_depth, assigned_level) for the current ancestor chain.
    stack: list[tuple[int, int]] = []
    for raw_depth, node in pairs:
        while stack and stack[-1][0] >= raw_depth:
            stack.pop()
        parent_level = stack[-1][1] if stack else -1
        include = not node.ignored
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
            }
        )
    if as_json:
        return json_module.dumps(items, indent=2)
    lines = []
    for item in items:
        indent = "  " * item["level"]
        ref_part = f"{item['ref']} " if item["ref"] else ""
        name_part = f' "{item["name"]}"' if item["name"] else ""
        href_part = f' href="{item["href"]}"' if item["href"] else ""
        lines.append(f"{indent}{ref_part}[{item['role']}]{name_part}{href_part}")
    return "\n".join(lines)


def snapshot(
    interactive: bool = False,
    compact: bool = False,
    depth: int | None = None,
    selector: str | None = None,
    with_urls: bool = False,
    as_json: bool = False,
) -> str:
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
        if with_urls:
            raw = d.evaluate(
                f"JSON.stringify([...document.querySelectorAll('[{_REF_ATTR}]')]"
                f".reduce((o, el) => (o[el.getAttribute('{_REF_ATTR}')] = el.href || null, o), {{}}))"
            )
            hrefs = json_module.loads(raw) if raw else {}

        return _render(levels, hrefs, as_json)

    return with_driver(_run)
