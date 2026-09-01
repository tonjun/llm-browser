# Command Reference

Complete reference for every `llm-browser` command. Command syntax and
grouping is modeled on [agent-browser](../docs/agent-browser/), but
everything here is implemented purely with what SeleniumBase's CDP-mode
API exposes (plus a few raw CDP calls for the snapshot/@ref system -
see [`snapshot-and-refs.md`](snapshot-and-refs.md)).

**Selectors:** every selector argument accepts a plain CSS selector or
an `@eN` ref produced by [`snapshot`](#snapshot). There is no `find
role/label/placeholder/testid` semantic-locator system (see
[Not supported](#not-supported-yet) below) - `click`/`hover` have a
`--text` flag as a partial substitute.

## Navigation

```bash
llm-browser open <url> [--headless]   # Launch (or reuse) the session and navigate
llm-browser close                     # Shut down the persistent session
llm-browser back                      # Go back
llm-browser forward                   # Go forward
llm-browser reload [--ignore-cache]   # Reload the current page
```

## Search

```bash
llm-browser search <engine> <query>
```

Drives straight to a known engine/site's query URL (no re-deriving a
search-box `@eN` ref every call) and returns a `snapshot -i -u` of the
results. `<engine>` is one of `google`, `bing`, `duckduckgo` (`ddg`),
`reddit`, `hn` (`hackernews`), or `github`. See
[`deep-research.md`](deep-research.md) for per-site caveats (e.g. why
`reddit` search targets `old.reddit.com`).

## Interaction

```bash
llm-browser click <sel>                 # Click
llm-browser click --text "Sign In"      # Click the first element matching this text
llm-browser click <sel> --gui           # Click via real OS pointer (PyAutoGUI); needs --headed
llm-browser dblclick <sel>              # Double-click (JS-dispatched; no native method)
llm-browser type <sel> <text>           # Type without clearing first
llm-browser fill <sel> <text>           # Clear, then type
llm-browser press <key> [--selector s]  # Press a key (default target: :focus)
llm-browser hover <sel>                 # Hover
llm-browser focus <sel>                 # Focus
llm-browser check <sel>                 # Check a checkbox (no-op if already checked)
llm-browser uncheck <sel>               # Uncheck a checkbox (no-op if already unchecked)
llm-browser select <sel> <value...>     # Select one or more dropdown options by value
llm-browser drag <src> <dst>            # Drag and drop
llm-browser upload <sel> <file...>      # Upload file(s) to a file input
llm-browser scroll <dir> [px]           # up | down | left | right | top | bottom
llm-browser scroll down --until-count <n> --selector <css> [--timeout s]  # scroll-and-collect
llm-browser scrollintoview <sel>        # Scroll an element into view
```

Caveats:
- `press` has no selector-less "send to whatever has focus" primitive
  from SeleniumBase; `:focus` (a valid CSS pseudo-class in Chrome)
  stands in for it, unlike agent-browser's true selector-less form.
- `check <sel>` and `uncheck <sel>` work around a SeleniumBase quirk:
  its own `is_checked()` raises `KeyError` (instead of returning
  `False`) for the common case of an unchecked box with no literal
  `checked` HTML attribute - handled internally, transparent to you.
- `select` with more than one value has no native multi-select helper;
  it's done via a small JS loop setting `.selected` on each matching
  `<option>` and firing one `change` event.
- `scroll left`/`right` have no dedicated SeleniumBase method; done via
  `window.scrollBy(...)`.
- `--until-count` formalizes the infinite-scroll pagination loop: scrolls
  down, prints the resulting element count, and repeats until `--selector`
  matches at least `<n>` elements, the count stops growing between scrolls
  (end of content), or `--timeout` (default 25s) elapses. Requires
  `--selector`.

## Wait

```bash
llm-browser wait <sel>                    # Wait for an element
llm-browser wait --ms <n>                 # Wait n milliseconds (dumb wait)
llm-browser wait --text "Success"         # Wait for text to appear
llm-browser wait --url "**/dashboard"     # Wait for the URL to match a glob pattern
llm-browser wait --fn "<js-bool-expr>"    # Wait for a JS expression to become truthy
llm-browser wait ... --timeout <seconds>  # Default: 25s
```

`--url` and `--fn` have no native SeleniumBase primitive; both poll
(`get_current_url()`/`evaluate()` every 200ms) until the condition is
met or the timeout elapses. `--load networkidle` (agent-browser's
post-navigation catch-all wait) isn't supported - see
[Not supported](#not-supported-yet).

## Get info

```bash
llm-browser get text <sel>        # Visible text
llm-browser get html <sel>        # innerHTML
llm-browser get value <sel>       # Input value
llm-browser get attr <sel> <name> # Any attribute
llm-browser get title             # Page title
llm-browser get url               # Current URL
llm-browser get count <sel>       # Count of matching elements
llm-browser get box <sel>         # Bounding box (x/y/width/height)
llm-browser get styles <sel> [--prop name]  # Computed styles (all, or one property)
llm-browser get cdp-url           # CDP WebSocket URL
```

`get count` and `get styles` have no dedicated SeleniumBase method:
count is done Python-side via `find_elements()` (no JS string
escaping needed); styles goes through a `getComputedStyle()` eval.

## Check state

```bash
llm-browser is visible <sel>   # Is the element visible?
llm-browser is enabled <sel>   # Is the element enabled (no `disabled` attribute)?
llm-browser is checked <sel>   # Is a checkbox/radio checked?
llm-browser is online          # Does the browser have network connectivity?
```

## Screenshots & PDF

```bash
llm-browser screenshot [path] [--full]   # Save a screenshot (--full for full-page)
llm-browser pdf <path>                   # Save the current page as a PDF
```

## Eval

```bash
llm-browser eval "<js>"        # Evaluate a JS expression
llm-browser eval --stdin       # Read the script from stdin (heredoc-friendly)
```

## Cookies & storage

```bash
llm-browser cookies get                 # All cookies
llm-browser cookies set <name> <value>  # Set a cookie (document.cookie write)
llm-browser cookies clear               # Clear all cookies

llm-browser storage get [key] [--session-storage]        # One key, or all of storage
llm-browser storage set <key> <value> [--session-storage]
llm-browser storage clear [--session-storage]
```

Storage defaults to `localStorage`; pass `--session-storage` for
`sessionStorage`. "Get all keys" and "clear" have no dedicated
SeleniumBase method for either store and go through a small eval.

## Tabs & windows

```bash
llm-browser tab new [url]              # Open a new tab
llm-browser tab new [url] --label docs # Open a new tab and label it "docs"
llm-browser tab new <url> --extract [--text] [--close]
                                  # Open a tab, wait for it to load, print its
                                  # main content as Markdown (or --text); --close
                                  # closes the tab again after extracting
llm-browser tab list             # List open tabs (index, target_id, label, url, title)
llm-browser tab switch <index|label>   # Switch to a tab by index (-1 = newest) or label
llm-browser tab close [index|label]    # Close a tab (default: current)
llm-browser window new [url]     # Open a new window
```

**Labels:** `--label` on `tab new` assigns a name you can later pass to
`tab switch`/`tab close` instead of an index. Labels are stored in
`~/.llm-browser/labels.json`, keyed on the tab's CDP `targetId`, which
stays stable for as long as that tab is open - so a label is the one
thing that *does* persist correctly across separate CLI invocations.
Labels must be unique (creating a second tab with an existing label
errors), are never auto-generated or rewritten, and are cleared when the
session closes (`llm-browser close`) since a fresh browser means fresh
targetIds.

**Active tab:** every command attaches to the daemon's browser fresh, but
the daemon remembers which tab was last made active (via `tab new` or
`tab switch`) in `~/.llm-browser/active_tab`, keyed on the same
`targetId`. So `llm-browser tab switch docs && llm-browser extract` now
extracts the `docs` tab, not just whichever tab happens to be newest -
`tab switch`/`tab new` set the tab every later command (`extract`,
`click`, `snapshot`, ...) operates on until something switches again.
Closing that tab clears the pointer, falling back to the newest
remaining tab.

**Important:** there is still no persistent `t1`/`t2` stable-index
counter like agent-browser's. `tab list`'s plain integer indices are
recomputed fresh on every call (mirroring SeleniumBase's own default),
so an index from one `tab list` call isn't guaranteed to point at the
same tab in a later call if tabs were opened or closed in between - use
a label instead when you need a reference that outlives a single
command.

## Snapshot & refs

```bash
llm-browser snapshot [-i] [-c] [-d N] [-s <css>] [-u] [--json]
```

- `-i, --interactive` - only interactive elements (links, buttons,
  inputs, ...)
- `-c, --compact` - drop empty structural/generic nodes
- `-d, --depth <n>` - limit tree depth
- `-s, --selector <css>` - scope to the subtree rooted at a CSS selector
- `-u, --urls` - include `href` on links
- `--json` - machine-readable output

See [`snapshot-and-refs.md`](snapshot-and-refs.md) for how `@eN` refs
work, how they're tagged onto elements, and their caveats (staleness on
navigation, no cross-origin iframe inlining).

## Misc

```bash
llm-browser highlight <sel>          # Highlight an element
llm-browser read [sel]               # Read the current page as plain text
llm-browser read <url> [--markdown]  # Fetch a URL directly (no browser tab)
llm-browser extract [--text]         # Readability-style main content of the open page (Markdown by default)
llm-browser internalize-links        # Rewrite target="_blank" links to same-tab
llm-browser tile-windows             # Tile open browser windows
llm-browser mfa-code [totp-key]      # Generate a TOTP code
llm-browser enter-mfa <sel> [totp-key]  # Generate and enter a TOTP code
llm-browser gui-hover-click <hover-sel> <click-sel>  # Hover then click via real OS pointer
```

`read` (no argument, or a CSS selector) reads the *currently open* page as
plain text via SeleniumBase's `get_beautiful_soup()`. `read <url>` instead
fetches that URL directly over HTTP - no browser tab involved, so no JS
rendering or session cookies - and runs it through `trafilatura` for
readability-style main-content extraction (plain text, or `--markdown`);
falls back to the raw fetched text if `trafilatura` can't find a
main-content region. This is a plain HTTP fetch, not agent-browser's
`llms.txt`-negotiation variant.

`extract` runs the same `trafilatura` extraction against the *currently
open* page's rendered HTML instead of a fresh fetch - use it (rather than
`read <url>`) for JS-heavy or logged-in pages where the content only
exists after the browser has rendered it. Falls back to the whole page's
plain text if `trafilatura` finds no main-content region.

See [`deep-research.md`](deep-research.md) for search + web-scraping
recipes built on `search`, `snapshot`, `get`, `eval`, `read`, `extract`,
and `scroll --until-count` — general and site-scoped search (Reddit, X,
Hacker News, GitHub), structured extraction, and pagination/infinite-scroll
patterns.

## Captcha solving

```bash
llm-browser solve-captcha [--gui]     # alias: click-captcha
```

Auto-detects and clicks past whichever of five vendors SeleniumBase
recognizes on the current page: **Cloudflare Turnstile**, **Google
reCAPTCHA v2 checkbox**, **hCaptcha** (including Incapsula-hosted), a
**DataDome slider**, and **Friendly Captcha**. `--gui` drives the real
OS pointer via PyAutoGUI instead of CDP-dispatched events (needed for
captcha types that check for genuine OS-level input) and requires a
real display (`--headed`, or the daemon's auto-started Xvfb on Linux).

This is best-effort and markup-shape-dependent - SeleniumBase
pattern-matches each vendor's known DOM structure, and it only clears
the checkbox/slider/token step, not challenges requiring actual content
solving (e.g. image grids). If nothing is detected, the command prints
a message and exits non-zero rather than claiming success.

**agent-browser has no captcha-solving capability at all** - this is a
genuine differentiator from using SeleniumBase underneath.

## Not supported (yet)

These need subsystems SeleniumBase's CDP-mode API doesn't expose (raw
CDP `Network`/`Emulation`/`Input`/`Tracing`/`Page.startScreencast`
domains), or a bigger architectural change (the daemon holding
persistent state across CLI invocations, not just a shared browser):

- `network route/unroute/requests/har` - network interception/HAR recording
- `set device/geo/offline/headers/media/credentials` - device/geo/media emulation
- `mouse move/down/up/wheel` - low-level synthetic mouse input (only
  PyAutoGUI-backed *real* OS pointer control is available, via `--gui`
  flags and `gui-hover-click`)
- `console`/`errors` capture, `dialog accept/dismiss/status` - would
  need the daemon itself to hold a persistent event buffer/handler
- `trace`/`profiler` start/stop, `record` (video capture)
- `frame <sel>` - iframe context switching
- `--session <name>` multi-session isolation, `state save/load`, `auth`
  vault, `plugin` system, `stream` (live viewport streaming), `react
  ...` devtools introspection, `vitals`, `a11y` audits, `batch`,
  `chat` (AI), `mcp` server, iOS/mobile provider

## Recommended next steps

Not part of this pass, but worth picking up next:

- **`find role/label/placeholder/testid` semantic locators.** Cheap to
  add now that `snapshot` already fetches the full accessibility tree -
  walk the same tree filtering by role/name instead of rendering it,
  tag the match, and delegate to the existing action commands.
- **Multi-session support** (`--session <name>`), generalizing
  `session.py`/`daemon.py` beyond today's single global daemon.
- Everything under [Not supported (yet)](#not-supported-yet) above,
  most of which would need raw CDP `Network`/`Emulation`/`Input`
  domain work similar to what `snapshot` already does for
  `Accessibility`/`DOM`.
- SeleniumBase-native extras not yet wired up as commands:
  `internalize-links`/`tile-windows`/`mfa-code`/`enter-mfa`/
  `gui-hover-click` are implemented; a `--gui` flag equivalent for
  more of the plain interaction commands (beyond `click`/`drag`) is a
  natural follow-up for sites with bot detection that flags
  CDP-dispatched input.
