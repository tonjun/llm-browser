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

## Project layout

```
src/llm_browser/
├── cli.py        # Typer CLI entrypoint - one command per action, grouped
│                 # into flat verbs (click, fill, ...) and noun sub-apps
│                 # (get, is, cookies, storage, tab, window)
├── browser.py    # SeleniumBase CDP Mode helpers: daemon lifecycle, the
│                 # attach-call-return pattern every command uses, and
│                 # the snapshot/@ref system
├── daemon.py     # Background process that owns the persistent Chrome instance
└── session.py    # State-file helpers coordinating the CLI and the daemon
```
