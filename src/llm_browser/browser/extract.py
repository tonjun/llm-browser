"""Extract: readability-style main-content extraction from the currently
open page. Complements fetch.fetch_url (plain HTTP, no JS) - this works on
whatever's actually rendered/logged-in in the browser session, needed for
JS-heavy sites (X, Reddit, ...)."""

from __future__ import annotations

import time
from pathlib import Path

import trafilatura
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser import session
from llm_browser.browser.core import with_driver


def extract_content(markdown: bool = True) -> str:
    def _run(d: CDPMethods) -> str:
        html = d.get_page_source()
        url = d.get_current_url()
        fmt = "markdown" if markdown else "txt"
        extracted = trafilatura.extract(html, url=url, output_format=fmt)
        # trafilatura's default fallback extractors (readability-lxml,
        # justext) can badly mis-segment heavily-nested, boilerplate-heavy
        # pages (e.g. old.reddit.com threads), returning a short excerpt
        # that skips most of the actual content. Its own "fast" algorithm
        # handles those pages correctly, so compare the two and keep
        # whichever is longer.
        fast = trafilatura.extract(html, url=url, output_format=fmt, fast=True)
        if fast is not None and (extracted is None or len(fast) > len(extracted)):
            extracted = fast
        if extracted is not None:
            return extracted
        # Fall back to plain text if trafilatura can't find a main-content
        # region (e.g. a non-article page).
        return d.get_beautiful_soup().get_text(" ", strip=True)

    return with_driver(_run)


def save_markdown(path: str | None = None) -> str:
    """Extract the current page as Markdown and write it to disk.

    Mirrors capture.screenshot's optional-path convention: with no path,
    a timestamped one is generated under the state dir. Useful for other
    tools to cache page content on disk.
    """
    target = path or str(session.state_dir() / f"page-{int(time.time() * 1000)}.md")
    content = extract_content(markdown=True)
    Path(target).write_text(content)
    return target
