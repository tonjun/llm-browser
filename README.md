# llm-browser

[![CI](https://github.com/tonjun/llm-browser/actions/workflows/ci.yml/badge.svg)](https://github.com/tonjun/llm-browser/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/badge/managed%20with-uv-de5fe9.svg)](https://astral.sh)

**A stealth browser CLI for LLM agents.** Drive a real Chrome that anti-bot and
captcha systems don't flag, through a handful of plain shell commands: navigate,
snapshot the page as an accessibility tree with stable `@eN` refs, then act on
those refs (click, fill, get text, ...). Built for an agent to call from a
shell, but just as usable as a scripted CLI.

```console
$ llm-browser open https://news.ycombinator.com
$ llm-browser snapshot -i
- link "Hacker News" [ref=e1]
- link "new" [ref=e2]
...
$ llm-browser click @e2
$ llm-browser extract          # main content of the page, as Markdown
$ llm-browser close
```

## Contents

- [Why llm-browser](#why-llm-browser)
- [Install](#install)
- [Quick start](#quick-start)
- [What it can do](#what-it-can-do)
- [Deep research (search + scraping)](#deep-research-search--scraping)
- [Use it from an agent (Claude Code and others)](#use-it-from-an-agent-claude-code-and-others)
- [Files and privacy](#files-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Responsible use](#responsible-use)
- [Contributing](#contributing)
- [License](#license)

## Why llm-browser

- **Shell-first.** No server, SDK or protocol to wire up. If your agent can run
  a command, it can browse.
- **Refs instead of selectors.** `snapshot -i` returns a compact list of
  interactive elements tagged `@e1`, `@e2`, ...; every other command accepts
  those refs (or a plain CSS selector). Far less to read than raw HTML.
- **Stealth by default.** Runs a real Chrome that anti-bot systems don't flag,
  and can detect and click through supported captchas.
- **Persistent session.** The first `open` starts a background Chrome; later
  commands reuse it, so logins, cookies and tabs carry across commands.
- **Research helpers built in.** Search engines and sites (Google, Reddit, X,
  Hacker News, GitHub, ...), readability-style extraction, structured post and
  comment JSON, infinite-scroll pagination.

It is deliberately smaller than a general test framework such as Playwright; see
[`commands.md`](src/llm_browser/skills/llm-browser/docs/commands.md#not-supported-yet)
for what is intentionally left out.

## Install

Requires **macOS or Linux**, **Python 3.11+**, and a local **Google Chrome**
(other Chromium-based browsers may work but aren't tested). Windows is not
supported. Sessions rely on POSIX `flock` and process groups.

**Standalone CLI, no clone needed.** Installs [`uv`](https://astral.sh) if it
isn't already on PATH, then installs `llm-browser` as a global tool:

```bash
curl -fsSL https://raw.githubusercontent.com/tonjun/llm-browser/main/install.sh | sh
```

**Already have `uv`?**

```bash
uv tool install git+https://github.com/tonjun/llm-browser
```

**Prefer `pipx` / `pip`?**

```bash
pipx install git+https://github.com/tonjun/llm-browser
# or: pip install --user git+https://github.com/tonjun/llm-browser
```

Check it worked with `llm-browser --version`. To upgrade, re-run the same
command with `uv tool install --force ...` (or `pipx install --force ...`).

Want to hack on it? See [Contributing](#contributing).

## Quick start

```bash
llm-browser open https://example.com
llm-browser snapshot -i              # interactive elements only, with @eN refs
llm-browser click @e1                # act on a ref from the snapshot
llm-browser fill @e2 "hello@example.com"
llm-browser get text @e3
llm-browser close                    # always close when you're done
```

(Running from a repo clone without installing? Prefix each command with
`uv run`, e.g. `uv run llm-browser open https://example.com`.)

Useful flags: `open --headless` (no window) and `open --headed` (force a real
window). They only apply to the `open` that starts the session; run `close`
first to switch modes.

**Refs go stale.** `@e1`, `@e2`, ... are assigned fresh on every `snapshot` and
stop working once the page navigates or re-renders. Re-snapshot after any
page-changing action. Details in
[`snapshot-and-refs.md`](src/llm_browser/skills/llm-browser/docs/snapshot-and-refs.md).

**Sessions persist.** How the background daemon works, and how to run several
isolated sessions with `LLM_BROWSER_HOME`, is in
[`persistent-sessions.md`](src/llm_browser/skills/llm-browser/docs/persistent-sessions.md).

## What it can do

Run `llm-browser --help` (or `llm-browser <command> --help`) for everything.
The full reference, with examples and the list of unsupported features, is
[`commands.md`](src/llm_browser/skills/llm-browser/docs/commands.md).

| Area | Commands |
|---|---|
| Navigate | `open`, `close`, `back`, `forward`, `reload` |
| Read the page | `snapshot`, `get text/html/value/...`, `read`, `extract`, `post`, `is ...` |
| Interact | `click`, `dblclick`, `fill`, `type`, `press`, `hover`, `check`, `select`, `drag`, `upload`, `scroll` |
| Wait | `wait` (element, text, URL, timeout, JS condition) |
| Search & scrape | `search`, `extract`, `save-markdown`, `read <url>`, `tab new --extract` |
| Capture | `screenshot`, `pdf` |
| State | `cookies`, `storage`, `tab`, `window`, `eval` |
| Anti-bot | `click-captcha` / `solve-captcha`, `mfa-code`, `enter-mfa`, `gui-hover-click` |
| Agents | `skills list/get/install` |

## Deep research (search + scraping)

```bash
llm-browser search reddit "your query"     # search a known engine/site
llm-browser search google "your query" --json --pages 3  # merge the first 3 result pages as JSON
llm-browser extract                        # main content of the open page, as Markdown
llm-browser post                           # structured JSON for a post: author, date, title, content, media, nested comments
llm-browser tab new https://example.com --extract --close  # open a URL, extract as Markdown, close the tab
llm-browser save-markdown notes.md         # save the open page's main content as Markdown to disk
llm-browser read https://example.com --markdown  # fetch a URL directly, no browser tab
llm-browser scroll down --until-count 50 --selector ".item"  # infinite-scroll pagination
```

Recipes for site-scoped search, structured extraction and pagination are in
[`deep-research.md`](src/llm_browser/skills/llm-browser/docs/deep-research.md).

## Use it from an agent (Claude Code and others)

The package bundles the `llm-browser` skill: how to drive the CLI correctly
(the core loop and the session model). A
second bundled skill, `search-results-extractor`, turns a search-results
snapshot into title/URL/snippet lists; read it with
`llm-browser skills get search-results-extractor`.

```bash
llm-browser skills list                    # bundled skills + descriptions
llm-browser skills get llm-browser --full  # SKILL.md plus its docs/*.md, as plain text
llm-browser skills install                 # install llm-browser into ~/.claude/skills (Claude Code)
llm-browser skills install --project       # ...or into ./.claude/skills
llm-browser skills install --force         # overwrite / refresh after upgrading the CLI
```

**Claude Code:** `skills install` is all you need; inside a clone of this repo
the skill is already loaded through the committed symlink at
`.claude/skills/llm-browser`.

**Any other agent** (Cursor, Codex, a custom loop, ...): the CLI is plain
shell, so put the output of `llm-browser skills get llm-browser --full` in your
agent's instructions or rules file and allow it to run `llm-browser`.

The canonical text lives in
[`src/llm_browser/skills/llm-browser/SKILL.md`](src/llm_browser/skills/llm-browser/SKILL.md);
edit that when the command surface changes.

## Files and privacy

Everything lives under `~/.llm-browser/` (override with `LLM_BROWSER_HOME`):

| Path | What it holds |
|---|---|
| `profile/` | The Chrome profile: **cookies, logins and local storage persist here** between sessions |
| `screenshots/`, `pages/` | Default output of `screenshot` and `save-markdown` (they are not cleaned up automatically) |
| `daemon.log` | Output of the background browser, for debugging |
| `session.json`, `*.lock` | Bookkeeping for the running session |

Treat it like a browser profile. To wipe everything: `llm-browser close`, then
`rm -rf ~/.llm-browser`. While a session is running, Chrome's DevTools port is
open on the local machine; see [SECURITY.md](SECURITY.md).

## Troubleshooting

| Symptom | Try |
|---|---|
| `No running session` error, or a command hangs on a stale session | `llm-browser close`, then `open` again |
| Chrome won't start | Make sure Google Chrome is installed; read the tail of `~/.llm-browser/daemon.log` |
| Chrome profile locked / `SingletonLock` errors | `llm-browser close` (kills any orphaned Chrome), or use a fresh `LLM_BROWSER_HOME` |
| `error: ...` with no detail | Re-run with `LLM_BROWSER_DEBUG=1` for the full traceback |
| `--headless` / `--headed` seemingly ignored | They only apply to the `open` that starts the session; `close` first |
| A `@eN` ref "doesn't resolve" | Refs are per-snapshot; run `snapshot` again |
| Linux server, no display | Default runs Chrome inside an invisible Xvfb display; pass `--headless` if that fails |
| Still stuck | [Open an issue](https://github.com/tonjun/llm-browser/issues/new/choose) with your OS, Chrome version and the commands you ran |

## Responsible use

llm-browser is a general-purpose automation tool, and its stealth and captcha
features exist so agents can do legitimate work (research, testing, accessibility
checks, your own accounts) on sites that block naive bots. Use it only on
sites and accounts you are authorized to access, respect each site's terms of
service, `robots.txt` and applicable laws, and rate-limit your requests. You are
responsible for how you use it. The software is provided as is, without warranty
(see [LICENSE](LICENSE)).

## Contributing

Contributions are welcome. After cloning:

```bash
uv sync
make test    # run the test suite (pytest, no Chrome needed)
make lint    # ruff check
make format  # ruff format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide: where code and tests
live, how to add a command, commit style and the PR checklist. Please open an
issue first for anything beyond a small fix. This project follows the
[Code of Conduct](CODE_OF_CONDUCT.md). Release notes are in
[CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE). Built on [SeleniumBase](https://seleniumbase.io/).
