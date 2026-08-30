# Snapshot & the `@ref` System

`llm-browser snapshot` renders the page's accessibility tree and hands
back stable `@eN` refs you can pass to any other selector-taking
command (`click @e2`, `fill @e3 "..."`, `get text @e1`, ...) instead of
writing CSS. This is modeled on agent-browser's snapshot/ref workflow;
this doc covers how it's implemented here, on top of raw CDP calls
SeleniumBase's high-level API doesn't wrap, and the caveats that follow
from that.

## How it works

1. **Fetch the accessibility tree.** `snapshot` calls CDP's
   `Accessibility.getFullAXTree` directly (via `driver.page.send(...)`
   and the `mycdp` protocol client SeleniumBase already vendors - see
   [implementation notes](#implementation-notes) below), giving a flat
   list of `AXNode`s with role, name, ignored flag, parent/child ids,
   and a `backendDOMNodeId` linking each accessibility node back to its
   DOM element.
2. **Walk and filter.** The flat list is rebuilt into a tree and walked
   depth-first, applying `-i`/`-c`/`-d`/`-s`. Nodes CDP marks
   `ignored` are always dropped from the rendered output, but their
   *children* are re-attached to the nearest kept ancestor so the tree
   doesn't lose entire branches just because an intermediate wrapper
   node has no accessible role. A few more removals happen
   unconditionally (no flag needed, since none of them lose real
   information): the `RootWebArea` root and `InlineTextBox` nodes
   (Chrome's internal echo of its parent `StaticText`'s name) are
   always dropped, and an unnamed `generic`/`none` node that doesn't
   branch (0 or 1 children - a no-op wrapper `<div>` or an
   empty/decorative leaf) is collapsed, re-attaching its child (if any)
   the same way an ignored node's children are. `-c/--compact` layers
   on top of this for anyone who wants to go further, dropping *any*
   unnamed `generic`/`none` node regardless of child count.
3. **Tag each kept, element-backed node.** For every node that survives
   filtering and maps to a real DOM Element, the CLI:
   - pushes its `backendDOMNodeId` to the frontend
     (`DOM.pushNodesByBackendIdsToFrontend`) to get a live `NodeId`, then
   - sets a `data-llmb-ref="eN"` attribute on it (`DOM.setAttributeValue`).
4. **Render.** The walked tree prints as a YAML-style dash-list, one
   node per line: `- role "name" [state=value, ref=eN, href="..."]`
   (or `--json` for structured output), e.g.:

   ```
   - link "About" [ref=e1]
   - button "Google apps" [expanded=false, ref=e19]
   ```

   The bracketed attrs are trailing and optional - omitted entirely
   when a node has none. Refs (`ref=eN`) come from the tagging step
   above; `href=` only appears with `-u/--urls`. A short allowlist of
   ARIA state properties (`expanded`, `checked`, `pressed`, `selected`,
   `disabled`, `required`, `readonly`, `level`) is also surfaced when
   present on the node, ahead of `ref`/`href` in that fixed order -
   see `_STATE_PROPS_ORDER` in `snapshot.py`. `expanded`/`checked`/
   `pressed`/`selected`/`level` print at any value since they reflect a
   widget's current toggle position either way; `disabled`/`required`/
   `readonly` behave like HTML boolean attributes and only print when
   `true` (an untoggled `required=false` on every input would just be
   noise). Boolean values print lowercase (`expanded=false`, not
   Python's `False`).

Every other command's selector argument then just resolves `@eN` to the
CSS selector `[data-llmb-ref="eN"]` and flows through the normal
SeleniumBase methods unchanged - there's no separate ref-resolution
code path anywhere else in the CLI.

## Caveats

- **Refs go stale on navigation or re-render.** Every `snapshot` call
  clears any `data-llmb-ref` attributes left by a previous snapshot
  before assigning new ones, and refs are never auto-refreshed. Run
  `snapshot` again after any page-changing action (a click that
  navigates, a form submit, an SPA re-render) before using a ref from
  before that action - exactly like agent-browser's own documented
  behavior.
- **No cross-origin iframe inlining.** `Accessibility.getFullAXTree` is
  scoped to the top frame's target; agent-browser auto-inlines
  same-origin iframe content into one snapshot, which would need
  per-frame AX tree fetches merged into the parent tree (each iframe is
  its own CDP target/session). This isn't implemented - `snapshot`
  covers the main page only.
- **Tagging is an observable DOM mutation.** Setting
  `data-llmb-ref` on elements is visible to page JS inspecting its own
  attributes, and a strict CSP could in principle interfere with CDP's
  ability to mutate attributes. Acceptable for an automation tool, but
  worth knowing if you're testing anti-automation defenses.
- **Not every accessibility node is taggable.** Chrome's internal
  `StaticText`/`InlineTextBox`/`LineBreak` roles correspond to DOM Text
  nodes, not Elements - CDP can't set an attribute on those, so they're
  never assigned a ref (they still appear in the tree for readability).
  `RootWebArea`'s `backendDOMNodeId` refers to the `#document` node
  itself, not `<html>`, for the same reason - see the next section for
  why that one matters more than it sounds.

## Implementation notes

Two non-obvious things had to be worked out against the actual
installed `seleniumbase` package (not just its documented method list),
in case this needs revisiting after a SeleniumBase upgrade:

- **`sb_cdp.Chrome`'s wrapped methods don't cover the `Accessibility`
  or raw `DOM` domains at all.** `sb_cdp.Chrome` is a thin sync wrapper
  where `self.page` is a CDP `Tab`/`Connection` with `async def
  send(cdp_command)`, and SeleniumBase vendors `mycdp` (a full typed
  CDP protocol client) as a transitive dependency. `mycdp.accessibility`
  isn't re-exported by `mycdp/__init__.py` and needs an explicit
  `import mycdp.accessibility`; `mycdp.dom` is exported normally.
- **`DOM.getDocument()` must be called once before backend node ids
  resolve.** Without it, `DOM.pushNodesByBackendIdsToFrontend` silently
  comes back empty for every node - not an exception, just nothing to
  work with. `snapshot` calls it once per run, right after enabling the
  `DOM` domain.
- **Calling `DOM.setAttributeValue` on the wrong node type kills the
  whole CDP connection, not just that one call.** The connection's
  `send()` wraps every command in a broad `try/except Exception:
  await self.aclose()` with no re-raise - so a single CDP protocol
  error (e.g. attempting to set an attribute on `RootWebArea`'s backing
  `#document` node, which isn't an Element) closes the websocket
  outright, and every subsequent command on that connection silently
  returns `None` instead of raising. This is why `RootWebArea` is
  explicitly excluded from tagging (see [Caveats](#caveats)) rather
  than merely skipped after failing once - by the time it failed, it
  would already be too late for every node after it in the same
  snapshot. If you see snapshot's tagging mysteriously affecting only
  the first node or two, suspect the same failure mode for whatever
  role triggered it.
