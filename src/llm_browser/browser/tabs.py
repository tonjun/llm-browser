"""Tabs & windows."""

from __future__ import annotations

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser import session
from llm_browser.browser import extract
from llm_browser.browser.core import with_driver


def _mark_active(d: CDPMethods):
    """Record the newest tab as the one later commands should attach to.

    Without this, a tab opened here would only be "current" for this one
    process - the next `llm-browser` invocation reattaches from scratch and
    falls back to whatever ``driver.tabs[-1]`` happens to be at that point
    (see ``browser/core.py``'s ``_active_page``).
    """
    tab = d.get_tabs()[-1]
    target_id = getattr(tab.target, "target_id", None)
    if target_id is not None:
        session.write_active_tab(target_id)
    return tab


def tab_new(url: str | None = None, label: str | None = None) -> None:
    def _run(d: CDPMethods) -> None:
        if label is not None and label in session.read_labels():
            raise ValueError(f"Label {label!r} is already in use.")
        d.open_new_tab(url)
        tab = _mark_active(d)
        if label is not None:
            target_id = getattr(tab.target, "target_id", None)
            labels = session.read_labels()
            labels[label] = target_id
            session.write_labels(labels)

    with_driver(_run)


def tab_new_extract(url: str, markdown: bool = True, close: bool = False) -> str:
    """Open ``url`` in a new tab, extract its main content, and optionally
    close the tab again. See ``extract.extract_content`` for the extraction
    logic itself; this just composes ``tab_new`` + extract (+ close) since
    ``with_driver`` always attaches to the newest tab."""

    def _open(d: CDPMethods) -> None:
        d.open_new_tab(url)
        _mark_active(d)
        d.sleep(2)

    with_driver(_open)
    content = extract.extract_content(markdown=markdown)
    if close:
        tab_close()
    return content


def tab_list() -> list[dict]:
    def _run(d: CDPMethods) -> list[dict]:
        tabs = d.get_tabs()
        labels_by_target = {v: k for k, v in session.read_labels().items()}
        result = []
        for i, t in enumerate(tabs):
            target = getattr(t, "target", None)
            target_id = getattr(target, "target_id", None)
            result.append(
                {
                    "index": i,
                    "url": getattr(target, "url", None),
                    "title": getattr(target, "title", None),
                    "target_id": target_id,
                    "label": labels_by_target.get(target_id),
                }
            )
        return result

    return with_driver(_run)


def _resolve_tab(ref: str, tabs: list):
    """Resolve `ref` (a `tab list` index, or a `--label` name) to a Tab.

    There's no persistent `t1`/`t2` counter like agent-browser's (see
    ``docs/commands.md``'s tabs section for why), but a label survives
    across CLI invocations by pointing at the tab's CDP `targetId`, which
    stays stable for as long as the tab itself is open.
    """
    try:
        return tabs[int(ref)]
    except ValueError:
        pass  # not an int - fall through to label lookup
    except IndexError:
        raise ValueError(f"No tab at index {ref!r}.") from None

    target_id = session.read_labels().get(ref)
    if target_id is None:
        raise ValueError(f"No tab with index or label {ref!r}.")
    for t in tabs:
        if getattr(t.target, "target_id", None) == target_id:
            return t
    # The label's tab is gone (closed outside of `tab close`) - drop the
    # now-dangling mapping rather than leave it to fail the same way again.
    labels = session.read_labels()
    labels.pop(ref, None)
    session.write_labels(labels)
    raise ValueError(f"Label {ref!r} points to a tab that no longer exists.")


def tab_switch(ref: str) -> None:
    def _run(d: CDPMethods) -> None:
        tab = _resolve_tab(ref, d.get_tabs())
        d.switch_to_tab(tab)
        target_id = getattr(tab.target, "target_id", None)
        if target_id is not None:
            session.write_active_tab(target_id)

    with_driver(_run)


def tab_close(ref: str | None = None) -> None:
    def _run(d: CDPMethods) -> None:
        target_id = None
        if ref is not None:
            tab = _resolve_tab(ref, d.get_tabs())
            target_id = getattr(tab.target, "target_id", None)
            d.switch_to_tab(tab)
        else:
            target_id = getattr(d.get_active_tab().target, "target_id", None)
        d.close_active_tab()
        if target_id is not None:
            labels = session.read_labels()
            stale = [k for k, v in labels.items() if v == target_id]
            if stale:
                for k in stale:
                    del labels[k]
                session.write_labels(labels)
            # The closed tab can no longer be attached to - forget it so
            # later commands fall back to the newest remaining tab instead
            # of erroring on a targetId that's gone.
            if session.read_active_tab() == target_id:
                session.clear_active_tab()

    with_driver(_run)


def window_new(url: str | None = None) -> None:
    with_driver(lambda d: d.open_new_window(url))
