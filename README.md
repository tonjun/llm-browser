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
```

## Project layout

```
src/llm_browser/
├── cli.py        # Typer CLI entrypoint
└── browser.py    # SeleniumBase CDP Mode helper
```
