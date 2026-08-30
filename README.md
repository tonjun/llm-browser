# llm-browser

A Python CLI for browser automation, built on
[SeleniumBase](https://seleniumbase.io/) CDP Mode, with a command
surface modeled on [agent-browser](https://github.com) - navigate,
snapshot the page as an accessibility tree with stable `@eN` refs, then
act on those refs with plain commands.

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
