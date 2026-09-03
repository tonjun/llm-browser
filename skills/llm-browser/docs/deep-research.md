# Deep Research: Search & Scraping

A playbook for the loop deep-research workflows repeat constantly: search a
source, land on results, extract structured data, and repeat across pages,
threads, or sites. It's built out of the commands documented in
[`commands.md`](commands.md) — `search`, `extract`, and `scroll
--until-count` are dedicated shortcuts for the three steps of that loop;
the rest is the same `open`/`snapshot`/`fill`/`eval`/`read` toolkit used
everywhere else in this CLI. See [`snapshot-and-refs.md`](snapshot-and-refs.md)
for how `@eN` refs work if you're new to the ref model.

## General web search

```bash
uv run llm-browser search google "llm browser automation"
uv run llm-browser search bing "llm browser automation"
uv run llm-browser search duckduckgo "llm browser automation"
```

`search <engine> <query>` opens the engine's query URL directly and
returns a `snapshot -i -u` of the results in one call — no re-deriving a
search-box `@eN` ref each time. `-u` on that snapshot means result
`href`s are already in the output, so you can `open` a result's link or
`click @eN` on it without a second `get attr @eN href` round-trip.

If you need to drive a search box by hand instead (a site not in
`search`'s known-engine list, or you need intermediate steps like
changing a filter first), the underlying loop is: `open` the homepage,
`snapshot -i` to find the search box's ref, `fill` the query, `press
Enter`, then re-`snapshot -i -u`.

## Site-scoped search

Search UIs and result markup vary a lot per site, and URL query-param
formats aren't documented or stable — so prefer driving the site's own
search box via `snapshot -i` over guessing a query-string URL. Each site
below follows the same core loop; only the caveats differ.

### Reddit (reddit.com)

```bash
uv run llm-browser search reddit "your query"
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
  more comments"`) to expand them first. Once expanded, `snapshot -m`
  renders nested replies as nested blockquotes (`>`, `> >`, ...) so the
  thread structure stays readable; if a page's comments aren't exposed as
  nested list items in the accessibility tree, fall back to walking
  `.comment` nodes via `eval` instead.
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
uv run llm-browser search hn "your query"
```

- Plain server-rendered HTML on both `news.ycombinator.com` and the Algolia
  search front end — the easiest site here to scrape reliably with
  `snapshot` or a plain `eval` selector query.
- **Prefer the Algolia HN Search API directly** when you just need
  structured data (title, points, comment count, url) rather than rendered
  HTML: `read https://hn.algolia.com/api/v1/search?query=<query>` fetches
  the JSON response as text (no browser tab needed) — parse it directly
  rather than scraping rendered HTML. No auth, no rate-limit surprises.

### GitHub (code / issue search)

```bash
uv run llm-browser search github "your query"
```

Unauthenticated search works for public repos but is rate limited quickly.
For anything beyond a handful of lookups, prefer the
[GitHub REST/GraphQL API](https://docs.github.com/en/rest) (via `eval` +
`fetch()` with a token in a header, or an external HTTP client outside this
CLI) over scraping the search UI.

### Any other site

`search` only knows the engines above. For anything else, don't guess
query-string formats — `open` the site's homepage or search page,
`snapshot -i` to find the search input's ref, `fill` + `press Enter`, then
`snapshot -i -u` the results. It's robust to markup/URL differences
because it never depends on either.

## Web scraping / extraction patterns

These build directly on commands already documented in
[`commands.md`](commands.md) — nothing new to install or enable.

**Readability-style main content** — `extract` pulls the article/post body
out of the *currently open* page (JS-rendered, logged-in session and all)
as Markdown, using `trafilatura`'s main-content detection so you don't
have to hand-write a selector or `eval` script for "just the article
text":

```bash
uv run llm-browser open https://example.com/some-article
uv run llm-browser extract              # Markdown
uv run llm-browser extract --text       # plain text
```

For a URL you don't need to actually visit in the browser (no JS, no
login required), `read <url>` does the same extraction via a plain HTTP
fetch instead — cheaper for batch lookups:

```bash
uv run llm-browser read https://example.com/some-article --markdown
```

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

`scroll --until-count` formalizes the scroll-and-collect loop: it keeps
scrolling down until a selector matches at least N elements, growth stalls
(end of content), or a timeout elapses.

```bash
uv run llm-browser scroll down --until-count 50 --selector ".athing" --timeout 20
uv run llm-browser snapshot -i --json     # or eval, to collect the loaded items
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
