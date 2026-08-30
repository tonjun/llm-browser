"""Extract: readability-style main-content extraction from the currently
open page. Complements fetch.fetch_url (plain HTTP, no JS) - this works on
whatever's actually rendered/logged-in in the browser session, needed for
JS-heavy sites (X, Reddit, ...)."""

from __future__ import annotations

import trafilatura
from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import with_driver


def extract_content(markdown: bool = True) -> str:
    def _run(d: CDPMethods) -> str:
        html = d.get_page_source()
        url = d.get_current_url()
        fmt = "markdown" if markdown else "txt"
        extracted = trafilatura.extract(html, url=url, output_format=fmt)
        if extracted is not None:
            return extracted
        # Fall back to plain text if trafilatura can't find a main-content
        # region (e.g. a non-article page).
        return d.get_beautiful_soup().get_text(" ", strip=True)

    return with_driver(_run)
