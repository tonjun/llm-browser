# Contributing to llm-browser

Thanks for considering a contribution. This is a small CLI, so the bar
for a good PR is mostly: does it match the existing structure, and is
it tested.

## Getting set up

You need Python 3.11+ (see `.python-version`) and [`uv`](https://astral.sh). Chrome is only
needed if you want to try the CLI against a real browser; the test suite is fully mocked and
runs in about ten seconds without it. macOS and Linux only.

Clone the repo and sync dependencies:

```bash
git clone https://github.com/tonjun/llm-browser
cd llm-browser
uv sync
```

`uv run llm-browser ...` now runs your working tree, so you don't need
to reinstall between edits.

## Dev loop

```bash
make test    # run the test suite (pytest)
make lint    # ruff check
make format  # ruff format
```

Run `make lint` and `make test` before opening a PR — both are quick. CI runs the same two
commands on Linux and macOS.

Please be kind: this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Where things live

- `src/llm_browser/cli.py` — Typer CLI entrypoint; wires up sub-apps
  (`get`, `is`, `cookies`, `storage`, `tab`, `window`) and each
  `commands/*.py` module.
- `src/llm_browser/commands/` — Typer command definitions (argument
  parsing only). One module per topic.
- `src/llm_browser/browser/` — SeleniumBase CDP Mode logic, one module
  per topic, mirroring `commands/` 1:1 (e.g. `commands/navigation.py` ↔
  `browser/navigation.py`).
- `src/llm_browser/daemon.py` / `session.py` — the persistent
  background-Chrome model shared by every command.
- `tests/` mirrors `src/llm_browser/` the same way — a new
  `browser/foo.py` should come with `tests/browser/test_foo.py`.

See
[`src/llm_browser/skills/llm-browser/docs/`](src/llm_browser/skills/llm-browser/docs/) for how the CLI
is meant to be driven (persistent sessions, snapshot/ref model, deep
research recipes).

## Adding or changing a command

1. Add the browser-level logic in `browser/<topic>.py`.
2. Add the Typer command in `commands/<topic>.py`, calling into it.
3. Add tests under `tests/browser/` and `tests/commands/`.
4. If the change affects how an agent should use the CLI, update
   [`src/llm_browser/skills/llm-browser/SKILL.md`](src/llm_browser/skills/llm-browser/SKILL.md) and/or
   the relevant doc under `src/llm_browser/skills/llm-browser/docs/` — that's the
   canonical, version-controlled copy Claude Code loads as a project
   skill.

## Commits and pull requests

- Branch from `main`; keep each PR focused on one change.
- Commit messages are short and imperative, optionally starting with a gitmoji
  (`✨ Add support for ...`, `🐛 Fix ...`, `🧹 ...`); PRs are squash-merged with the PR number appended.
- Add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md) for anything user-visible.
- The [PR template](.github/PULL_REQUEST_TEMPLATE.md) has the checklist.

## Reporting bugs / requesting features

Open a GitHub issue with repro steps (a URL and the commands you ran,
where possible); the issue templates ask for the details we need. Report security problems privately, see
[SECURITY.md](SECURITY.md). For anything beyond a small fix, please open an issue
first to discuss the approach before sending a PR.

## Code style

Formatting and lint rules are enforced by `ruff` (`make format`,
`make lint`); there's no separate style guide to memorize.
