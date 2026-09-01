"""Tabs & windows."""

from __future__ import annotations

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser import extract
from llm_browser.browser.core import with_driver


def tab_new(url: str | None = None) -> None:
    with_driver(lambda d: d.open_new_tab(url))


def tab_new_extract(url: str, markdown: bool = True, close: bool = False) -> str:
    """Open ``url`` in a new tab, extract its main content, and optionally
    close the tab again. See ``extract.extract_content`` for the extraction
    logic itself; this just composes ``tab_new`` + extract (+ close) since
    ``with_driver`` always attaches to the newest tab."""

    def _open(d: CDPMethods) -> None:
        d.open_new_tab(url)
        d.sleep(2)

    with_driver(_open)
    content = extract.extract_content(markdown=markdown)
    if close:
        with_driver(lambda d: d.close_active_tab())
    return content


def tab_list() -> list[dict]:
    def _run(d: CDPMethods) -> list[dict]:
        tabs = d.get_tabs()
        result = []
        for i, t in enumerate(tabs):
            target = getattr(t, "target", None)
            result.append(
                {
                    "index": i,
                    "url": getattr(target, "url", None),
                    "title": getattr(target, "title", None),
                }
            )
        return result

    return with_driver(_run)


def tab_switch(index: int) -> None:
    # SeleniumBase only accepts an int index (or a raw Tab object) here -
    # there's no persistent `t1`/`t2`/label system like agent-browser's;
    # use the index from `tab list`.
    with_driver(lambda d: d.switch_to_tab(index))


def tab_close(index: int | None = None) -> None:
    def _run(d: CDPMethods) -> None:
        if index is not None:
            d.switch_to_tab(index)
        d.close_active_tab()

    with_driver(_run)


def window_new(url: str | None = None) -> None:
    with_driver(lambda d: d.open_new_window(url))
