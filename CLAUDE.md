# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync            # install deps into .venv (do this first)
make test           # uv run pytest
make lint           # uv run ruff check .
make format         # uv run ruff format .
make run ARGS="..." # uv run llm-browser ...  (run the CLI from the working tree)
```

Single test: `uv run pytest tests/browser/test_navigation.py::test_go_back`

Run `make lint` and `make test` before considering a change done — both are fast.

## Architecture

The CLI has three layers, mirrored 1:1 by topic (`navigation`, `interaction`,
`wait`, `search`, `extract`, `info`, `state`, `capture`, `evaluate`,
`storage`, `tabs`, `snapshot`, `misc`, `captcha`, `gui`, `fetch`):

- `cli.py` — Typer entrypoint. Builds `app` plus noun sub-apps (`get`,
  `is`, `cookies`, `storage`, `tab`, `window`) and calls each
  `commands/<topic>.py`'s `register()` to attach its commands.
- `commands/<topic>.py` — Typer command definitions (argument parsing
  only); each calls straight into the matching `browser/<topic>.py`.
- `browser/<topic>.py` — the actual SeleniumBase CDP Mode logic.

`tests/` mirrors `src/llm_browser/` the same way (`tests/browser/test_foo.py`
tests `browser/foo.py`). Adding or changing a command means touching all three
matching files plus tests — see CONTRIBUTING.md for the checklist, and update
`src/llm_browser/skills/llm-browser/SKILL.md` / `src/llm_browser/skills/llm-browser/docs/*.md` (the
canonical, version-controlled agent-facing docs) when the change affects how
an agent should drive the CLI.

### Persistent session model (`browser/core.py`, `daemon.py`, `session.py`)

The browser is not launched per-command. The first `open` spawns
`daemon.py` as a detached background process (`start_new_session=True`,
its own process group) that owns a single Chrome instance via
SeleniumBase's CDP mode and blocks until it's signalled to stop or Chrome's
debug port goes away. Coordination
between the daemon and later short-lived CLI invocations happens purely
through state files under `~/.llm-browser/` (`session.py`) — there is no
in-memory IPC, since every `llm-browser` command is a fresh process:

- `session.json` — daemon pid + CDP host/port (`SessionState`).
- `command.lock` — an `flock`-based lock (`session.command_lock()`) every
  `with_driver()` call takes, serializing concurrent CLI invocations
  against the daemon's shared Chrome (reentrant per-thread so a command
  that wraps several `with_driver` calls, e.g. `tab_new_extract`, doesn't
  deadlock on itself).
- `active_tab` — the CDP `targetId` `tab switch` pointed at, so tab choice
  carries across process boundaries (`browser/core.py::_active_page`).
- `labels.json` — tab labels.

Every command other than `open`/`close` is a stateless
attach-call-return against the daemon's Chrome: `browser/core.py::_attach`
reconnects over CDP without touching the current page (unlike
`sb_cdp.Chrome(...)`, which forces a navigation to `about:blank` on
construction), runs one call, and never `driver.quit()`s — that would just
close this process's CDP connection, not the shared browser. Only
`llm-browser close` (SIGTERM to the daemon, `killpg` fallback if it doesn't
exit in time) actually tears Chrome down.

### Snapshot & `@ref` system (`browser/snapshot.py`)

`snapshot` reads the page's accessibility tree via raw CDP (the
`Accessibility`/`DOM` domains, not wrapped by `sb_cdp`) and tags each
included element in the live DOM with `data-llmb-ref="eN"`. Every other
command's selector argument is resolved by `resolve_selector()`
(`browser/core.py`) which rewrites a bare `@eN` to
`[data-llmb-ref="eN"]` and passes anything else through unchanged as a
plain CSS selector — there's no separate ref-handling code path elsewhere.
Refs are only valid for the snapshot that produced them; a new `snapshot`
clears old `data-llmb-ref` attributes first. See
`src/llm_browser/skills/llm-browser/docs/snapshot-and-refs.md` for the full model
including known CDP quirks it works around (e.g. text-node AX roles
having no taggable DOM element, `RootWebArea` backing the `#document`
node rather than `<html>`).

### Command surface reference

The CLI's command surface is deliberately modeled on `agent-browser` (an
npm CLI with the same `@eN`-ref snapshot idea) but is a separate, smaller
implementation — don't assume a flag exists just because `agent-browser`
has it. `src/llm_browser/skills/llm-browser/docs/commands.md` documents the full command
reference plus what's intentionally *not* implemented and why (useful
context before adding a new command that might duplicate something
already ruled out).

## Claude Code skill

`src/llm_browser/skills/llm-browser/SKILL.md` (plus `src/llm_browser/skills/llm-browser/docs/`) is the
canonical, version-controlled doc teaching an agent how to drive this CLI
correctly. The README says it's wired up via a committed symlink at
`.claude/skills/llm-browser` — if that symlink is missing in your checkout,
recreate it with:

```bash
mkdir -p .claude/skills
ln -s ../../src/llm_browser/skills/llm-browser .claude/skills/llm-browser
```

Any change to the command surface that affects how an agent should use the
CLI should be reflected in `SKILL.md`/`docs/*.md`, not just the code.
