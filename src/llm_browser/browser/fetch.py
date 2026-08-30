"""URL-fetch mode: plain HTTP fetch + readability-style extraction,
deliberately independent of the browser session (no with_driver here) -
for cheap batch research fetches that don't need JS rendering or login."""

from __future__ import annotations

import requests
import trafilatura

_UA = "Mozilla/5.0 (compatible; llm-browser/0.1)"


def fetch_url(url: str, markdown: bool = False) -> str:
    resp = requests.get(url, timeout=15, headers={"User-Agent": _UA})
    resp.raise_for_status()
    fmt = "markdown" if markdown else "txt"
    extracted = trafilatura.extract(resp.text, url=url, output_format=fmt)
    # Fall back to the raw fetched text if trafilatura can't find a
    # main-content region (e.g. a non-article page).
    return extracted if extracted is not None else resp.text
