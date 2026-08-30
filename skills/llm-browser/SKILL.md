---
name: llm-browser
description: Browser automation via the llm-browser CLI (SeleniumBase CDP mode) — navigate, snapshot the page as an accessibility tree with @eN refs, click/fill/type, extract text, screenshot, manage cookies/storage/tabs, solve captchas. Use whenever the user asks to interact with a website, fill a form, click something, extract data, take a screenshot, log into a site, or automate any browser task in this project.
allowed-tools: Bash(uv run llm-browser:*)
---

# llm-browser

A Python CLI for browser automation, built on [SeleniumBase](https://seleniumbase.io/)
CDP mode. Its command surface is modeled on the `agent-browser` npm CLI
(navigate → snapshot the page as an accessibility tree with stable
`@eN` refs → act on those refs), but it's a separate implementation
with a smaller surface and some real differences — don't assume an
`agent-browser` flag exists here just because it sounds familiar. When
in doubt, check [`docs/commands.md`](../../docs/commands.md), the
source of truth for every command and flag.

All commands below are invoked as `uv run llm-browser <command>` from
the repo root.

## The core loop

```bash
uv run llm-browser open https://example.com
uv run llm-browser snapshot -i              # interactive elements only, with @eN refs
uv run llm-browser click @e1                # act on a ref from the snapshot
uv run llm-browser fill @e2 "hello@example.com"
uv run llm-browser get text @e3
uv run llm-browser close
```

**Refs go stale on navigation or re-render.** `@e1`, `@e2`, ... are
assigned fresh on every `snapshot` call. After any page-changing
action (a click that navigates, a form submit, an SPA re-render),
re-snapshot before using a ref again — a stale ref just won't resolve.
See [`docs/snapshot-and-refs.md`](../../docs/snapshot-and-refs.md) for
the full model (how refs are tagged, why cross-origin iframes aren't
inlined, etc.).

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
  silently ignored (with a printed note) — run `uv run llm-browser
  close` first if you need to switch modes.
- `uv run llm-browser close` shuts the daemon (and Chrome) down.
  Always close when a task is finished so a background Chrome instance
  doesn't linger.
- **There is no `--session <name>` multi-session isolation** like
  agent-browser has. There's exactly one global daemon/session — don't
  try to pass a session flag or run two isolated browser contexts side
  by side.

Full detail (state layout under `~/.llm-browser/`, crash recovery,
race handling): [`docs/persistent-sessions.md`](../../docs/persistent-sessions.md).

## Reading a page

```bash
uv run llm-browser snapshot                    # full accessibility tree
uv run llm-browser snapshot -i                 # interactive elements only (preferred)
uv run llm-browser snapshot -c                 # compact (drop empty structural nodes)
uv run llm-browser snapshot -d 3                # cap depth at 3 levels
uv run llm-browser snapshot -s "#main"          # scope to a CSS selector
uv run llm-browser snapshot -u                  # include href urls on links
uv run llm-browser snapshot -i --json           # machine-readable output
```

```bash
uv run llm-browser get text @e1        # visible text
uv run llm-browser get html @e1        # innerHTML
uv run llm-browser get value @e1       # input value
uv run llm-browser get attr @e1 href   # any attribute
uv run llm-browser get title           # page title
uv run llm-browser get url             # current URL
uv run llm-browser get count ".item"   # count of matching elements
uv run llm-browser get box @e1         # bounding box
uv run llm-browser get styles @e1      # computed styles (all, or --prop name)
uv run llm-browser get cdp-url         # CDP WebSocket URL

uv run llm-browser read                # read the *currently open* page as plain text
```

`read` only reads whatever page is currently open in the session —
unlike agent-browser's `read <url>`, there's no fetch-without-a-browser
/ `llms.txt`-negotiation variant here.

## Interacting

```bash
uv run llm-browser click @e1                 # click
uv run llm-browser click --text "Sign In"    # click the first element matching this text
uv run llm-browser dblclick @e1              # double-click
uv run llm-browser hover @e1                 # hover
uv run llm-browser focus @e1                 # focus
uv run llm-browser fill @e2 "hello"          # clear then type
uv run llm-browser type @e2 " world"         # type without clearing
uv run llm-browser press Enter               # press a key (default target: :focus)
uv run llm-browser check @e3                 # check a checkbox
uv run llm-browser uncheck @e3               # uncheck
uv run llm-browser select @e4 value1 value2  # select one or more dropdown options by value
uv run llm-browser upload @e5 file1.pdf      # upload file(s) to a file input
uv run llm-browser scroll down 500           # up | down | left | right | top | bottom
uv run llm-browser scrollintoview @e1        # scroll an element into view
uv run llm-browser drag @e1 @e2              # drag and drop
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
uv run llm-browser wait @e1                  # wait for an element
uv run llm-browser wait --ms 2000            # dumb wait, milliseconds (last resort)
uv run llm-browser wait --text "Success"     # wait for text to appear
uv run llm-browser wait --url "**/dashboard" # wait for URL to match a glob pattern
uv run llm-browser wait --fn "document.readyState === 'complete'"  # wait for a JS bool expr
uv run llm-browser wait ... --timeout 25     # seconds; default is 25
```

**There is no `--load networkidle` catch-all** like agent-browser has.
After a navigation or SPA transition, use `wait --url "**/pattern"` or
`wait --text "..."` for the thing you actually expect to change,
instead of reaching for a network-idle wait that doesn't exist here.

## Common workflows

### Log in

```bash
uv run llm-browser open https://app.example.com/login
uv run llm-browser snapshot -i
# Pick the email/password/submit refs out of the snapshot, then:
uv run llm-browser fill @e3 "user@example.com"
uv run llm-browser fill @e4 "hunter2"
uv run llm-browser click @e5
uv run llm-browser wait --url "**/dashboard"
uv run llm-browser snapshot -i
```

### Extract data

```bash
uv run llm-browser snapshot -i --json > page.json   # structured, best for reasoning over content

uv run llm-browser snapshot -i
uv run llm-browser get text @e5                      # targeted extraction with a ref

cat <<'EOF' | uv run llm-browser eval --stdin
const rows = document.querySelectorAll("table tbody tr");
Array.from(rows).map(r => ({
  name: r.cells[0].innerText,
  price: r.cells[1].innerText,
}));
EOF
```

Prefer `eval --stdin` (heredoc) for any JS with quotes or special
characters; inline `eval "..."` only works for simple expressions.

### Screenshot

```bash
uv run llm-browser screenshot            # viewport screenshot, printed path
uv run llm-browser screenshot page.png   # specific path
uv run llm-browser pdf output.pdf        # save the page as a PDF
```

**`--full` (full-page, stitched screenshot) is not supported** —
SeleniumBase's CDP-mode API has no native full-page capture method,
only viewport screenshots. Don't pass `--full`.

## Cookies, storage, tabs, windows

```bash
uv run llm-browser cookies get
uv run llm-browser cookies set <name> <value>
uv run llm-browser cookies clear

uv run llm-browser storage get [key] [--session-storage]   # defaults to localStorage
uv run llm-browser storage set <key> <value> [--session-storage]
uv run llm-browser storage clear [--session-storage]

uv run llm-browser tab new [url]
uv run llm-browser tab list
uv run llm-browser tab switch <index>   # -1 = newest
uv run llm-browser tab close [index]
uv run llm-browser window new [url]
```

**Tab state isn't persistent across CLI invocations.** There's no
`t1`/`t2`/label system like agent-browser's — every command attaches
to the daemon fresh and picks its most-recently-opened tab by default.
`tab switch` only affects that one command's own attach, not any state
later commands will see. Treat multi-tab workflows as best-effort.

## Captcha solving

```bash
uv run llm-browser solve-captcha         # alias: click-captcha
uv run llm-browser solve-captcha --gui   # real OS pointer, needs --headed
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

## Full reference

- [`docs/commands.md`](../../docs/commands.md) — every command and
  flag, plus the full "not supported" rationale
- [`docs/persistent-sessions.md`](../../docs/persistent-sessions.md) —
  how the background daemon works
- [`docs/snapshot-and-refs.md`](../../docs/snapshot-and-refs.md) — how
  `@eN` refs are generated and their caveats
