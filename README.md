# llm-browser

A Python CLI for browser automation, built on
[SeleniumBase](https://seleniumbase.io/) CDP Mode, with a command
surface modeled on [agent-browser](https://github.com) - navigate,
snapshot the page as an accessibility tree with stable `@eN` refs, then
act on those refs with plain commands.

## Install

```bash
uv sync
```

## The core loop

```bash
uv run llm-browser open https://example.com
uv run llm-browser snapshot -i              # interactive elements only, with @eN refs
uv run llm-browser click @e1                # act on a ref from the snapshot
uv run llm-browser fill @e2 "hello@example.com"
uv run llm-browser get text @e3
uv run llm-browser close
```

The browser session is persistent: the first `open` starts a background
Chrome instance and leaves it running, and later commands reuse it
instead of launching a new one. Refs (`@e1`, `@e2`, ...) are assigned
fresh on every `snapshot` call and go stale the moment the page
navigates or re-renders - re-snapshot after any page-changing action.
See [`docs/snapshot-and-refs.md`](docs/snapshot-and-refs.md) for the
full ref-staleness model and its caveats.

See [`docs/commands.md`](docs/commands.md) for the full command
reference (interaction, get/is, cookies/storage, tabs, captcha
solving, and more), including what agent-browser supports that isn't
implemented here and why.

## Usage

```bash
uv run llm-browser open https://example.com
uv run llm-browser open https://example.com --headless
uv run llm-browser close
```

See [`docs/persistent-sessions.md`](docs/persistent-sessions.md) for how
the persistent daemon works and `llm-browser close` to shut it down.

## Deep research (search + scraping)

For workflows that search engines and specific sites (Reddit, X/Twitter,
Hacker News, GitHub, ...) and then extract structured data from the
results, see [`docs/deep-research.md`](docs/deep-research.md) — recipes for
site-scoped search, structured extraction via `snapshot --json`/`eval`, and
handling pagination/infinite scroll.

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
