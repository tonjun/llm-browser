---
name: llm-browser
description: Browser automation via the llm-browser CLI (SeleniumBase CDP mode) — navigate, snapshot the page as an accessibility tree with @eN refs, click/fill/type, search the web, scrape/extract page data, screenshot, manage cookies/storage/tabs, solve captchas. Use whenever the user asks to interact with a website, fill a form, click something, search the web, scrape or extract data from a page, take a screenshot, log into a site, or automate any browser task.
allowed-tools: Bash(uv run llm-browser:*), Bash(llm-browser:*)
---

# llm-browser

A Python CLI for browser automation, built on [SeleniumBase](https://seleniumbase.io/)
CDP mode. Its command surface is modeled on the `agent-browser` npm CLI
(navigate → snapshot the page as an accessibility tree with stable
`@eN` refs → act on those refs), but it's a separate implementation
with a smaller surface and some real differences — don't assume an
`agent-browser` flag exists here just because it sounds familiar.

All commands below assume `llm-browser` is on PATH (`uv tool install .`
/ `pipx install .`). If you're working from a repo clone without a
global install, prefix each command with `uv run` instead (`uv run
llm-browser <command>`).

## The core loop

```bash
llm-browser open https://example.com
llm-browser snapshot -i              # interactive elements only, with @eN refs
llm-browser click @e1                # act on a ref from the snapshot
llm-browser fill @e2 "hello@example.com"
llm-browser get text @e3
llm-browser close
```

**Refs go stale on navigation or re-render.** `@e1`, `@e2`, ... are
assigned fresh on every `snapshot` call. After any page-changing
action (a click that navigates, a form submit, an SPA re-render),
re-snapshot before using a ref again — a stale ref just won't resolve.

Every selector argument accepts either a plain CSS selector or an
`@eN` ref — there's no separate ref-resolution path to think about.

## Persistent session model

The first `open` starts a background daemon that launches Chrome and
keeps it running; every later command reconnects to that same daemon
over CDP instead of starting a new browser. This means commands in the
same task share state (cookies, logins, open tabs) without you having
to do anything — just call `open` again to navigate the existing
session.

- `--headless` only matters on the *first* `open` that spawns the
  daemon. If a session is already running, a later `--headless` is
  silently ignored (with a printed note) — run `llm-browser close`
  first if you need to switch modes.
- `llm-browser close` shuts the daemon (and Chrome) down.
  Always close when a task is finished so a background Chrome instance
  doesn't linger.
- **There is no `--session <name>` multi-session isolation** like
  agent-browser has. There's exactly one global daemon/session — don't
  try to pass a session flag or run two isolated browser contexts side
  by side.

## Reading a page

```bash
llm-browser snapshot                    # full accessibility tree
llm-browser snapshot -i                 # interactive elements only (preferred)
llm-browser snapshot -c                 # compact (drop empty structural nodes)
llm-browser snapshot -d 3                # cap depth at 3 levels
llm-browser snapshot -s "#main"          # scope to a CSS selector
llm-browser snapshot -u                  # include href urls on links
llm-browser snapshot -i --json           # machine-readable output
```

```bash
llm-browser get text @e1        # visible text
llm-browser get html @e1        # innerHTML
llm-browser get value @e1       # input value
llm-browser get attr @e1 href   # any attribute
llm-browser get title           # page title
llm-browser get url             # current URL
llm-browser get count ".item"   # count of matching elements
llm-browser get box @e1         # bounding box
llm-browser get styles @e1      # computed styles (all, or --prop name)
llm-browser get cdp-url         # CDP WebSocket URL

llm-browser read                # read the *currently open* page as plain text
llm-browser read <url>          # fetch a URL directly, no browser tab (--markdown for Markdown)
```

`read` with no argument (or a CSS selector) reads whatever page is
currently open in the session. `read <url>` fetches that URL directly
over plain HTTP instead — no JS rendering, no session cookies — similar
in spirit to agent-browser's `read <url>`, though without its
`llms.txt`-negotiation step.

## Interacting

```bash
llm-browser click @e1                 # click
llm-browser click --text "Sign In"    # click the first element matching this text
llm-browser dblclick @e1              # double-click
llm-browser hover @e1                 # hover
llm-browser focus @e1                 # focus
llm-browser fill @e2 "hello"          # clear then type
llm-browser type @e2 " world"         # type without clearing
llm-browser press Enter               # press a key (default target: :focus)
llm-browser check @e3                 # check a checkbox
llm-browser uncheck @e3               # uncheck
llm-browser select @e4 value1 value2  # select one or more dropdown options by value
llm-browser upload @e5 file1.pdf      # upload file(s) to a file input
llm-browser scroll down 500           # up | down | left | right | top | bottom
llm-browser scrollintoview @e1        # scroll an element into view
llm-browser drag @e1 @e2              # drag and drop
```

**No semantic-locator system.** agent-browser's `find role/text/label/
placeholder/testid` doesn't exist here. `click`/`hover --text "..."` is
the only partial substitute (matches on visible text). Prefer snapshot
+ `@eN` refs, or a raw CSS selector, for anything else.

**`--gui` flag** on `click`/`drag` (and the standalone
`gui-hover-click`) drives a *real* OS pointer via PyAutoGUI instead of
CDP-dispatched synthetic events — needed for bot-detection or captcha
flows that check for genuine input. Requires `--headed` (or the
daemon's auto-started Xvfb on Linux).

## Waiting

```bash
llm-browser wait @e1                  # wait for an element
llm-browser wait --ms 2000            # dumb wait, milliseconds (last resort)
llm-browser wait --text "Success"     # wait for text to appear
llm-browser wait --url "**/dashboard" # wait for URL to match a glob pattern
llm-browser wait --fn "document.readyState === 'complete'"  # wait for a JS bool expr
llm-browser wait ... --timeout 25     # seconds; default is 25
```

**There is no `--load networkidle` catch-all** like agent-browser has.
After a navigation or SPA transition, use `wait --url "**/pattern"` or
`wait --text "..."` for the thing you actually expect to change,
instead of reaching for a network-idle wait that doesn't exist here.

## Common workflows

### Log in

```bash
llm-browser open https://app.example.com/login
llm-browser snapshot -i
# Pick the email/password/submit refs out of the snapshot, then:
llm-browser fill @e3 "user@example.com"
llm-browser fill @e4 "hunter2"
llm-browser click @e5
llm-browser wait --url "**/dashboard"
llm-browser snapshot -i
```

### Search & deep research

```bash
llm-browser search bing "llm browser automation"
llm-browser search duckduckgo "llm browser automation"
```

`search <engine> <query>` opens the engine's query URL directly and
returns a `snapshot -i -u` of the results in one call — `-u` means result
`href`s are already in the output, so pull out links without a second
`get attr @eN href` round-trip, either `click @eN` on a result's ref or
`open` its href directly.

If a site isn't one of `search`'s known engines, drive its search box by
hand with the same underlying loop: `open` the homepage, `snapshot -i` to
find the search box's `@eN` ref, `fill` the query, `press Enter`, then
re-`snapshot -i -u`.

**Site-scoped search** (research sources beyond general web search) needs
per-site handling: Reddit (`search reddit ...`) — targets `old.reddit.com`
for scrapable markup, and expect comment threads to need "load more"
clicks; X/Twitter (not in `search`'s list — use the manual loop against
`x.com/search`) — most content needs a logged-in session (reuse cookies
via `cookies get/set`) plus a scroll-then-snapshot loop for its infinite
timeline; Hacker News (`search hn ...`) — plain HTML, or `read` the
Algolia search API URL directly for structured JSON; GitHub (`search
github ...`) — rate-limits fast unauthenticated, prefer its API beyond a
few lookups.

### Extract data

```bash
llm-browser extract                          # readability-style main content, Markdown
llm-browser extract --text                    # ...or plain text

llm-browser read https://example.com --markdown  # fetch + extract a URL directly, no browser tab

llm-browser snapshot -i --json > page.json   # structured, best for reasoning over content

llm-browser snapshot -i
llm-browser get text @e5                      # targeted extraction with a ref

cat <<'EOF' | llm-browser eval --stdin
const rows = document.querySelectorAll("table tbody tr");
Array.from(rows).map(r => ({
  name: r.cells[0].innerText,
  price: r.cells[1].innerText,
}));
EOF
```

Prefer `extract` for an article/post's main body (readability-style, no
selector needed), `read <url>` when you don't even need the page open in
the browser, `snapshot -i --json` for a structured, ref-addressable result
list, and `eval --stdin` (heredoc) for anything else custom. Inline `eval
"..."` only works for simple expressions.

### Screenshot

```bash
llm-browser screenshot            # viewport screenshot, printed path
llm-browser screenshot page.png   # specific path
llm-browser pdf output.pdf        # save the page as a PDF
```

**`--full` (full-page, stitched screenshot) is not supported** —
SeleniumBase's CDP-mode API has no native full-page capture method,
only viewport screenshots. Don't pass `--full`.

## Cookies, storage, tabs, windows

```bash
llm-browser cookies get
llm-browser cookies set <name> <value>
llm-browser cookies clear

llm-browser storage get [key] [--session-storage]   # defaults to localStorage
llm-browser storage set <key> <value> [--session-storage]
llm-browser storage clear [--session-storage]

llm-browser tab new [url]
llm-browser tab list
llm-browser tab switch <index>   # -1 = newest
llm-browser tab close [index]
llm-browser window new [url]
```

**Tab state isn't persistent across CLI invocations.** There's no
`t1`/`t2`/label system like agent-browser's — every command attaches
to the daemon fresh and picks its most-recently-opened tab by default.
`tab switch` only affects that one command's own attach, not any state
later commands will see. Treat multi-tab workflows as best-effort.

## Captcha solving

```bash
llm-browser solve-captcha         # alias: click-captcha
llm-browser solve-captcha --gui   # real OS pointer, needs --headed
```

Auto-detects and clicks past whichever of five vendors SeleniumBase
recognizes on the current page: Cloudflare Turnstile, Google reCAPTCHA
v2 checkbox, hCaptcha (including Incapsula-hosted), a DataDome slider,
and Friendly Captcha. Best-effort and markup-shape-dependent — clears
the checkbox/slider/token step only, not challenges requiring actual
content solving (e.g. image grids). Exits non-zero with a message if
nothing is detected, rather than claiming success. This is a genuine
capability agent-browser doesn't have at all.

## Not supported

These need lower-level browser subsystems this CLI doesn't wire up
yet, or a bigger architectural change. Don't invent flags for them —
if the task needs one of these, say so instead of guessing a command:

- Network interception / HAR recording (`network route/unroute/requests/har`)
- Device/geo/media/offline emulation (`set device/geo/offline/media`)
- Low-level synthetic mouse (`mouse move/down/up/wheel`) — only
  PyAutoGUI-backed real OS pointer control exists, via `--gui` flags
- Console/error capture, JS dialog handling (`console`, `errors`,
  `dialog accept/dismiss/status`)
- Tracing/profiling, video recording (`trace`, `profiler`, `record`)
- Iframe context switching (`frame <sel>`)
- Full-page screenshots (`screenshot --full`)
- `--session <name>` multi-session isolation, `state save/load`, auth
  vault, plugin system, live-stream viewport, React devtools
  introspection, `vitals`, `a11y` audits, `batch`, an MCP server, or a
  `find role/label/placeholder/testid` semantic-locator system
