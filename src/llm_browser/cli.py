"""Typer CLI entrypoint for llm-browser.

Command surface modeled on agent-browser's CLI (see
``docs/agent-browser/`` for the original) but implemented purely with
what SeleniumBase's CDP-mode API exposes - see ``docs/commands.md``
for the full reference, including what's *not* supported and why.

This module only builds the Typer app and its sub-apps and wires up
each topic's commands via its ``commands/*.py`` module's ``register()``
- the actual command implementations live in
:mod:`llm_browser.commands` (Typer arg parsing) and
:mod:`llm_browser.browser` (CDP logic).
"""

from __future__ import annotations

import os
import sys

import typer

from llm_browser import __version__
from llm_browser.commands import (
    captcha,
    capture,
    evaluate,
    extract,
    info,
    interaction,
    misc,
    navigation,
    post,
    search,
    skills,
    snapshot,
    state,
    storage,
    tabs,
    wait,
)

app = typer.Typer(
    help="llm-browser: browser automation via SeleniumBase CDP Mode.",
    # No Rich tracebacks: they run to 50+ lines and dump every frame's
    # locals - including the text an agent just passed to `fill`, cookie
    # values and TOTP keys - for what is usually a one-line "element not
    # found" / "no running session". `run()` below prints just the message.
    pretty_exceptions_enable=False,
    epilog="Examples:\n\n"
    "  llm-browser open https://example.com\n\n"
    "  llm-browser snapshot -i\n\n"
    "  llm-browser click @e1\n\n"
    '  llm-browser fill @e2 "hello@example.com"\n\n'
    "  llm-browser get text @e3\n\n"
    "  llm-browser close",
)

get_app = typer.Typer(help="Get info from the page.")
is_app = typer.Typer(help="Check element state.")
cookies_app = typer.Typer(help="Manage cookies.")
storage_app = typer.Typer(help="Manage local/session storage.")
tab_app = typer.Typer(help="Manage tabs.")
window_app = typer.Typer(help="Manage windows.")
skills_app = typer.Typer(help="Show and install the bundled Claude Code skills.")


def _version_callback(value: bool) -> None:
    if value:
        print(f"llm-browser {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


app.add_typer(get_app, name="get")
app.add_typer(is_app, name="is")
app.add_typer(cookies_app, name="cookies")
app.add_typer(storage_app, name="storage")
app.add_typer(tab_app, name="tab")
app.add_typer(window_app, name="window")
app.add_typer(skills_app, name="skills")

navigation.register(app)
interaction.register(app)
wait.register(app)
search.register(app)
extract.register(app)
post.register(app)
info.register(get_app)
state.register(is_app)
capture.register(app)
evaluate.register(app)
storage.register(cookies_app, storage_app)
tabs.register(tab_app, window_app)
snapshot.register(app)
misc.register(app)
captcha.register(app)
skills.register(skills_app)


def run() -> None:
    """Console-script entrypoint: ``app()`` with concise error reporting.

    Any exception escaping a command is printed as a single ``error: ...``
    line on stderr with exit status 1, so an agent reading the output gets
    the message and nothing else. Set ``LLM_BROWSER_DEBUG=1`` to get the
    full traceback instead.
    """
    try:
        app()
    except Exception as exc:
        if os.environ.get("LLM_BROWSER_DEBUG"):
            raise
        print(f"error: {format_error(exc)}", file=sys.stderr)
        sys.exit(1)


def format_error(exc: BaseException) -> str:
    """One-line message for ``exc``; falls back to the type name if empty."""
    message = " ".join(str(exc).split())
    return message or type(exc).__name__


if __name__ == "__main__":
    run()
