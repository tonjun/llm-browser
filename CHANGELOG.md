# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may
change the command surface).

## [Unreleased]

### Added
- Community files: `CHANGELOG.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and
  pull-request templates, and a CI workflow (lint + tests on Linux and macOS).
- Package metadata (keywords, classifiers, project URLs).

### Changed
- The bundled skill symlink at `.claude/skills/llm-browser` is now actually committed
  (it was previously gitignored).
- Running on Windows now exits with a clear "macOS and Linux only" message instead of
  an `ImportError` traceback.

## [0.8.0]

This entry summarizes the project's history up to 0.8.0; earlier versions were not tagged.

### Added
- `post` support for stomp.sg and for social media pages (Reddit, X, Hacker News,
  Facebook, Instagram, and generic forum/blog pages).
- `skills` command to list, show and install the bundled Claude Code skills.
- `search --pages N` to merge multiple result pages, and `--json` output for search engines.
- `--headed` flag for `open`, screenshot to stdout, scroll until stable, snapshot to Markdown,
  and tab management (`tab new/list/switch/close`).

### Fixed
- Concurrent tab handling, Google result extraction, DuckDuckGo search URL, snapshot issues.
