"""Search: drive straight to a known engine/site's query URL and snapshot
the results, instead of re-deriving a search-box @eN ref every call."""

from __future__ import annotations

import json
import sys
import time
from urllib.parse import quote_plus

from llm_browser.browser.core import open_url, with_driver
from llm_browser.browser.snapshot import snapshot

# Query-URL templates for engines/sites with stable, documented search
# params. See docs/deep-research.md for the per-site caveats (old.reddit.com
# over www.reddit.com, HN's Algolia front end, etc.) that motivated these
# specific choices.
_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "ddg": "https://html.duckduckgo.com/html/?q={q}",
    "reddit": "https://old.reddit.com/search/?q={q}",
    "hn": "https://hn.algolia.com/?q={q}",
    "hackernews": "https://hn.algolia.com/?q={q}",
    "github": "https://github.com/search?q={q}&type=code",
}

# Shared tail for every extractor: each engine snippet below builds `rows`
# (title/url/snippet triples, possibly with empty fields) and this collapses
# whitespace, drops incomplete rows and dedupes by URL.
_NORMALIZE_JS = """
const seen = new Set();
return rows
  .map(r => ({
    title: (r.title || '').replace(/\\s+/g, ' ').trim(),
    url: r.url || '',
    snippet: (r.snippet || '').replace(/\\s+/g, ' ').trim(),
  }))
  .filter(r => r.title && /^https?:/.test(r.url) && !seen.has(r.url) && seen.add(r.url));
"""

# Per-engine DOM extractors for `search --json`. Selectors were checked
# against the live sites; Google's class names are obfuscated, so it anchors
# on the stable `a > h3` structure rather than classes.
_EXTRACTORS = {
    "google": """
const rows = Array.from(document.querySelectorAll('#search a h3')).map(h => {
  const a = h.closest('a');
  // Climb to the smallest ancestor holding a snippet, but never into a
  // container that already holds another result's title.
  let c = a, snippet = '';
  for (let i = 0; i < 6 && c.parentElement; i++) {
    c = c.parentElement;
    if (c.querySelectorAll('h3').length > 1) break;
    const s = c.querySelector('[data-sncf], .VwiC3b');
    if (s) { snippet = s.textContent; break; }
  }
  return {title: h.textContent, url: a.href, snippet};
});
""",
    "bing": """
const rows = Array.from(document.querySelectorAll('li.b_algo')).map(li => {
  const a = li.querySelector('h2 a');
  let url = a ? a.href : '';
  // Result links are bing.com/ck/a redirects; the real URL is the `u`
  // param, base64url-encoded behind an "a1" prefix.
  try {
    const u = new URL(url).searchParams.get('u');
    if (u && u.startsWith('a1')) {
      url = atob(u.slice(2).replace(/-/g, '+').replace(/_/g, '/'));
    }
  } catch (e) {}
  const s = li.querySelector('.b_caption p, p.b_lineclamp2, .b_algoSlug, p');
  return {title: a ? a.textContent : '', url, snippet: s ? s.textContent : ''};
});
""",
    # DuckDuckGo's JS site links results directly.
    "duckduckgo": """
const rows = Array.from(document.querySelectorAll('article[data-testid=result]')).map(r => {
  const a = r.querySelector('h2 a');
  const s = r.querySelector('[data-result=snippet]');
  return {title: a ? a.textContent : '', url: a ? a.href : '', snippet: s ? s.textContent : ''};
});
""",
    # html.duckduckgo.com wraps result links in duckduckgo.com/l/?uddg=<url>.
    "ddg": """
const rows = Array.from(document.querySelectorAll('.result')).map(r => {
  const a = r.querySelector('a.result__a');
  const s = r.querySelector('.result__snippet');
  let url = a ? a.href : '';
  try {
    const u = new URL(url).searchParams.get('uddg');
    if (u) url = u;
  } catch (e) {}
  return {title: a ? a.textContent : '', url, snippet: s ? s.textContent : ''};
});
""",
}

_JSON_WAIT_SECONDS = 10.0
_JSON_POLL_INTERVAL = 0.5


def _extract_results(engine_key: str) -> list[dict[str, str]]:
    js = f"(() => {{ {_EXTRACTORS[engine_key]} {_NORMALIZE_JS} }})()"
    return with_driver(lambda d: d.evaluate(js)) or []


def search(engine: str, query: str, as_json: bool = False) -> str:
    key = engine.lower()
    if key not in _ENGINES:
        raise ValueError(
            f"Unknown search engine: {engine!r}. "
            f"Choose from: {', '.join(sorted(set(_ENGINES)))}"
        )
    if as_json and key not in _EXTRACTORS:
        raise ValueError(
            f"--json is not supported for {engine!r}. "
            f"Choose from: {', '.join(sorted(_EXTRACTORS))}"
        )
    url = _ENGINES[key].format(q=quote_plus(query))
    if not as_json:
        open_url(url)
    else:
        # quiet: open_url's title line would corrupt the JSON on stdout.
        open_url(url, quiet=True)
        # Result pages can still be rendering when open_url returns, so poll
        # until the extractor finds something.
        deadline = time.monotonic() + _JSON_WAIT_SECONDS
        results = _extract_results(key)
        while not results and time.monotonic() < deadline:
            time.sleep(_JSON_POLL_INTERVAL)
            results = _extract_results(key)
        if not results:
            print(
                "No results extracted (possible captcha/consent page); "
                "rerun without --json to see the page snapshot.",
                file=sys.stderr,
            )
        return json.dumps(results, ensure_ascii=False)
    # -i/--interactive would drop the result snippets: they're plain
    # StaticText/emphasis siblings of each result link, not one of
    # _INTERACTIVE_ROLES, so the interactive filter cuts them along with
    # the actual page chrome it's meant to remove. -c/--compact keeps them
    # (only unnamed empty structural wrappers are dropped) while still
    # collapsing no-op wrapper divs, so results keep their href *and* body
    # text.
    return snapshot(compact=True)
