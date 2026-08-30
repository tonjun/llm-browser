# llm-browser

A basic Python CLI scaffold for browser automation, built on
[SeleniumBase](https://seleniumbase.io/) CDP Mode.

## Install

```bash
uv sync
```

## Usage

```bash
uv run llm-browser open https://example.com
uv run llm-browser open https://example.com --headless
uv run llm-browser close
```

The browser session is persistent: the first `open` starts a background
Chrome instance and leaves it running, and later `open` calls reuse it
instead of launching a new one. See
[`docs/persistent-sessions.md`](docs/persistent-sessions.md) for how that
works and `llm-browser close` to shut it down.

## Project layout

```
src/llm_browser/
├── cli.py        # Typer CLI entrypoint
├── browser.py    # SeleniumBase CDP Mode helper (spawn-or-connect, navigate)
├── daemon.py     # Background process that owns the persistent Chrome instance
└── session.py    # State-file helpers coordinating the CLI and the daemon
```
