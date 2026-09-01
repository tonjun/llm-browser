# llm-browser

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/badge/managed%20with-uv-de5fe9.svg)](https://astral.sh)

A Python CLI for browser automation that drives a real Chrome browser
in stealth mode - undetected by anti-bot and captcha systems - and
exposes it as a small set of plain commands: navigate, snapshot the
page as an accessibility tree with stable `@eN` refs, then act on
those refs (click, fill, get text, ...). Built for driving from an LLM
agent, but works fine as a regular scripted CLI too.

## Contents

- [Install](#install)
- [Requirements](#requirements)
- [Built on](#built-on)
- [The core loop](#the-core-loop)
- [Usage](#usage)
- [Deep research (search + scraping)](#deep-research-search--scraping)
- [Claude Code skill](#claude-code-skill)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)

## Install

**Standalone CLI, no clone needed** — installs [`uv`](https://astral.sh) if
it's not already on PATH, then installs `llm-browser` as a global tool:

```bash
curl -fsSL https://raw.githubusercontent.com/tonjun/llm-browser/main/install.sh | sh
```

**Already have `uv`?** Skip the script:

```bash
uv tool install git+https://github.com/tonjun/llm-browser
```

**Prefer `pip`/`pipx` over `uv`?** Works too, no `uv` CLI required:

```bash
pipx install git+https://github.com/tonjun/llm-browser
# or: pip install --user git+https://github.com/tonjun/llm-browser
```

Any of the above gets you a `llm-browser` binary on PATH — commands below
assume that.

**Contributing to this repo?** Clone it and use the local dev loop instead,
which keeps `uv run llm-browser ...` in sync with your working tree:

```bash
uv sync
```

## Requirements

- Python 3.11+
- A local install of Google Chrome (driven in CDP Mode; other
  Chromium-based browsers may work but aren't tested)

## Built on

The stealth/undetected browsing and captcha-solving is
[SeleniumBase](https://seleniumbase.io/)'s CDP Mode + UC Mode doing
the heavy lifting - this CLI is a thin, LLM-friendly command layer on
top of it. The command surface itself is modeled on `agent-browser`,
a similar tool with the same `@eN`-ref snapshot model.

## The core loop

```bash
llm-browser open https://example.com
llm-browser snapshot -i              # interactive elements only, with @eN refs
llm-browser click @e1                # act on a ref from the snapshot
llm-browser fill @e2 "hello@example.com"
llm-browser get text @e3
llm-browser close
```

(Running from a repo clone without installing? Prefix each command with
`uv run` instead, e.g. `uv run llm-browser open https://example.com`.)

The browser session is persistent: the first `open` starts a background
Chrome instance and leaves it running, and later commands reuse it
instead of launching a new one. Refs (`@e1`, `@e2`, ...) are assigned
fresh on every `snapshot` call and go stale the moment the page
navigates or re-renders - re-snapshot after any page-changing action.
See [`skills/llm-browser/docs/snapshot-and-refs.md`](skills/llm-browser/docs/snapshot-and-refs.md) for the
full ref-staleness model and its caveats.

See [`skills/llm-browser/docs/commands.md`](skills/llm-browser/docs/commands.md) for the full command
reference (interaction, get/is, cookies/storage, tabs, captcha
solving, and more), including what agent-browser supports that isn't
implemented here and why.

## Usage

```bash
llm-browser open https://example.com
llm-browser open https://example.com --headless
llm-browser close
```

See [`skills/llm-browser/docs/persistent-sessions.md`](skills/llm-browser/docs/persistent-sessions.md) for how
the persistent daemon works and `llm-browser close` to shut it down.

## Deep research (search + scraping)

```bash
llm-browser search reddit "your query"     # search a known engine/site
llm-browser extract                        # main content of the open page, as Markdown
llm-browser tab new https://example.com --extract --close  # open a URL, extract as Markdown, close the tab
llm-browser save-markdown notes.md         # save the open page's main content as Markdown to disk
llm-browser read https://example.com --markdown  # fetch a URL directly, no browser tab
llm-browser scroll down --until-count 50 --selector ".item"  # infinite-scroll pagination
```

For workflows that search engines and specific sites (Reddit, X/Twitter,
Hacker News, GitHub, ...) and then extract structured data from the
results, see [`skills/llm-browser/docs/deep-research.md`](skills/llm-browser/docs/deep-research.md) — recipes for
site-scoped search, structured extraction, and handling pagination/infinite
scroll.

## Claude Code skill

[`skills/llm-browser/SKILL.md`](skills/llm-browser/SKILL.md) teaches
Claude Code (or any compatible agent) how to drive this CLI correctly
— the core loop, the persistent-session model, and the places this
tool's command surface diverges from `agent-browser`, the CLI its
commands are modeled on. It's already wired up via a committed symlink
at `.claude/skills/llm-browser`, which is where Claude Code looks for
project skills, so it loads automatically in this repo. If a clone
loses the symlink (e.g. a zip download, or a filesystem without
symlink support), recreate it with:

```bash
mkdir -p .claude/skills
ln -s ../../skills/llm-browser .claude/skills/llm-browser
```

Edit `skills/llm-browser/SKILL.md` itself when the command surface
changes — that's the canonical, version-controlled copy.

## Project layout

```
src/llm_browser/
├── cli.py          # Typer CLI entrypoint - builds the app + noun sub-apps
│                   # (get, is, cookies, storage, tab, window) and wires up
│                   # each commands/*.py module's register()
├── commands/       # Typer command definitions (arg parsing), one module
│                   # per topic, mirroring browser/ 1:1
├── browser/        # SeleniumBase CDP Mode helpers, one module per topic:
│   ├── core.py     #   daemon lifecycle + the attach-call-return pattern
│   │               #   every command uses (with_driver, resolve_selector)
│   ├── snapshot.py #   the accessibility-tree snapshot/@ref system
│   └── ...         #   navigation, interaction, wait, info, state, capture,
│                   #   evaluate, storage, tabs, misc, gui, captcha
├── daemon.py       # Background process that owns the persistent Chrome instance
└── session.py      # State-file helpers coordinating the CLI and the daemon
```

## Contributing

Contributions are welcome. After `uv sync` (see [Install](#install)):

```bash
make test    # run the test suite (pytest)
make lint    # ruff check
make format  # ruff format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, including
where tests and commands each live and what a good PR looks like.
Please open an issue first for anything beyond a small fix.

## License

[MIT](LICENSE)
