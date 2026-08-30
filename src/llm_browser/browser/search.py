"""Search: drive straight to a known engine/site's query URL and snapshot
the results, instead of re-deriving a search-box @eN ref every call."""

from __future__ import annotations

from urllib.parse import quote_plus

from llm_browser.browser.core import open_url
from llm_browser.browser.snapshot import snapshot

# Query-URL templates for engines/sites with stable, documented search
# params. See docs/deep-research.md for the per-site caveats (old.reddit.com
# over www.reddit.com, HN's Algolia front end, etc.) that motivated these
# specific choices.
_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "ddg": "https://duckduckgo.com/?q={q}",
    "reddit": "https://old.reddit.com/search/?q={q}",
    "hn": "https://hn.algolia.com/?q={q}",
    "hackernews": "https://hn.algolia.com/?q={q}",
    "github": "https://github.com/search?q={q}&type=code",
}


def search(engine: str, query: str) -> str:
    key = engine.lower()
    if key not in _ENGINES:
        raise ValueError(
            f"Unknown search engine: {engine!r}. "
            f"Choose from: {', '.join(sorted(set(_ENGINES)))}"
        )
    open_url(_ENGINES[key].format(q=quote_plus(query)))
    return snapshot(interactive=True, with_urls=True)
