# Deep Research: Search & Scraping

A playbook for the loop deep-research workflows repeat constantly: search a
source, land on results, extract structured data, and repeat across pages,
threads, or sites. It's built entirely out of the commands documented in
[`commands.md`](commands.md) — nothing here is a special mode, just a
recipe for combining `open`/`snapshot`/`fill`/`eval`/`read` well. See
[`snapshot-and-refs.md`](snapshot-and-refs.md) for how `@eN` refs work if
you're new to the ref model.

## General web search

```bash
# Google
uv run llm-browser open https://www.google.com
uv run llm-browser snapshot -i
# Pick the search box ref, then:
uv run llm-browser fill @e1 "llm browser automation"
uv run llm-browser press Enter
uv run llm-browser wait --text "results"
uv run llm-browser snapshot -i -u

# Bing / DuckDuckGo: same recipe, different homepage
uv run llm-browser open https://www.bing.com
uv run llm-browser open https://duckduckgo.com
```

Same `open` → `snapshot -i` (find the search box ref) → `fill` → `press
Enter` → re-`snapshot -i -u` loop each time. `-u` on the results snapshot
pulls result `href`s directly, so you can `open` a result's link or `click`
its ref without a second `get attr @eN href` round-trip.

## Site-scoped search

Search UIs and result markup vary a lot per site, and URL query-param
formats aren't documented or stable — so prefer driving the site's own
search box via `snapshot -i` over guessing a query-string URL. Each site
below follows the same core loop; only the caveats differ.

### Reddit (reddit.com)

```bash
uv run llm-browser open https://old.reddit.com/search/?q=your+query
uv run llm-browser snapshot -i -u
```

- **Prefer `old.reddit.com` over `www.reddit.com`** for scraping — its
  markup is plain server-rendered HTML with far less noise, so `snapshot`
  and `eval` extraction both work more reliably. `www.reddit.com` is a
  heavy client-rendered SPA.
- To search within one subreddit: `old.reddit.com/r/<subreddit>/search/
  ?q=<query>&restrict_sr=on`.
- **Comment threads are lazy-loaded and often collapsed.** A single
  `snapshot -i` on a post page won't surface nested/"load more comments"
  branches — click the "load more comments" links (`click --text "load
  more comments"`) or walk `.comment` nodes via `eval` after scrolling.
- No login is required for reading public posts/comments, but heavy,
  fast-paced scraping will get rate-limited or soft-blocked — pace requests
  and prefer the [official Reddit API](https://www.reddit.com/dev/api/)
  for anything beyond light, occasional lookups.

### X / Twitter (x.com)

```bash
uv run llm-browser open https://x.com/search?q=your%20query&src=typed_query
uv run llm-browser snapshot -i -u
```

- **Most search and profile content requires being logged in** — X gates
  timelines behind auth for anonymous/CDP-driven sessions far more
  aggressively than it used to. Use `cookies get`/`cookies set` (see
  [`commands.md`](commands.md#cookies--storage)) to reuse an authenticated
  session's cookies rather than trying to log in fresh each run.
- **Infinite-scroll timeline, not pagination.** A single `snapshot` only
  captures what's currently rendered. Extraction needs a scroll-then-
  snapshot loop — see [Pagination / infinite scroll](#pagination--infinite-scroll)
  below.
- Result and tweet markup uses opaque, frequently-changing class names;
  don't rely on CSS selectors for tweet content — use `snapshot -i` (role/
  text-based) or extract via `eval` against visible text nodes instead.

### Hacker News (news.ycombinator.com)

```bash
uv run llm-browser open "https://hn.algolia.com/?q=your+query"
uv run llm-browser snapshot -i -u
```

- Plain server-rendered HTML on both `news.ycombinator.com` and the Algolia
  search front end — the easiest site here to scrape reliably with
  `snapshot` or a plain `eval` selector query.
- **Prefer the Algolia HN Search API directly** when you just need
  structured data (title, points, comment count, url) rather than rendered
  HTML: `open` `https://hn.algolia.com/api/v1/search?query=<query>` and the
  JSON response renders as page text — `get text` or `read` pulls it back
  as a JSON string you can parse. No auth, no rate-limit surprises, no
  markup to fight.

### GitHub (code / issue search)

```bash
uv run llm-browser open "https://github.com/search?q=your+query&type=code"
uv run llm-browser snapshot -i -u
```

Same loop; unauthenticated search works for public repos but is rate
limited quickly. For anything beyond a handful of lookups, prefer the
[GitHub REST/GraphQL API](https://docs.github.com/en/rest) (via `eval` +
`fetch()` with a token in a header, or an external HTTP client outside this
CLI) over scraping the search UI.

### Any other site

Don't guess query-string formats. `open` the site's homepage or search
page, `snapshot -i` to find the search input's ref, `fill` + `press Enter`,
then `snapshot -i -u` the results — the same four-step loop as every
example above. It's robust to markup/URL differences because it never
depends on either.

## Web scraping / extraction patterns

These build directly on commands already documented in
[`commands.md`](commands.md) — nothing new to install or enable.

**Structured result lists** — `snapshot -i --json` gives ref-addressable,
machine-parseable output, best when you want to reason over a page's
content programmatically rather than eyeball it:

```bash
uv run llm-browser snapshot -i --json > page.json
```

**Custom structured extraction** — `eval --stdin` (heredoc) for anything a
snapshot doesn't shape the way you need, e.g. scraping a Reddit comment
tree or the currently-rendered posts in an X timeline:

```bash
cat <<'EOF' | uv run llm-browser eval --stdin
Array.from(document.querySelectorAll('[data-testid="tweet"]')).map(t => ({
  text: t.innerText,
  author: t.querySelector('[dir="ltr"] span')?.innerText,
}));
EOF
```

Prefer `eval --stdin` over inline `eval "..."` any time the script has
quotes or is more than a one-liner.

**Plain-text extraction** — `read` (no selector) reads the whole
currently-open page as plain text, or `read <sel>` scopes to a subtree.
Good for "just summarize this article", where structure doesn't matter.

**Cheap sanity checks** — a single targeted `get text @eN` is often faster
than a full snapshot when you already know which ref you want.

### Pagination / infinite scroll

There's no built-in "scroll until N results" command — script the loop
yourself:

```bash
uv run llm-browser scroll down 2000
uv run llm-browser wait --ms 500          # let lazy content render
uv run llm-browser snapshot -i --json     # or eval to collect new items
# repeat, de-duping against what you already collected, until no new
# content appears or you've reached the depth you need
```

For sites with real "next page" links/buttons instead of infinite scroll,
prefer `click`-ing that control (or `open`-ing the next-page URL, if the
result set exposed one via `-u`) over scrolling — it's more deterministic.

### Respect the source

- Honor `robots.txt` and each site's terms of service.
- Pace requests — don't hammer a single host in a tight loop; add `wait
  --ms` between actions on rate-limit-sensitive sites (Reddit, X).
- Prefer an official API (Reddit API, HN Algolia API, GitHub API) over
  scraping rendered HTML whenever one exists — it's more stable, faster,
  and less likely to get the session blocked.

## See also

- [`commands.md`](commands.md) — full command/flag reference for every
  command used above.
- [`snapshot-and-refs.md`](snapshot-and-refs.md) — how `@eN` refs are
  generated, tagged, and go stale.
- [`persistent-sessions.md`](persistent-sessions.md) — how the background
  session/daemon keeps cookies and login state across commands.
