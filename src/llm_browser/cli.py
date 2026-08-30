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

import typer

from llm_browser.commands import (
    capture,
    captcha,
    evaluate,
    info,
    interaction,
    misc,
    navigation,
    snapshot,
    state,
    storage,
    tabs,
    wait,
)

app = typer.Typer(help="llm-browser: browser automation via SeleniumBase CDP Mode.")

get_app = typer.Typer(help="Get info from the page.")
is_app = typer.Typer(help="Check element state.")
cookies_app = typer.Typer(help="Manage cookies.")
storage_app = typer.Typer(help="Manage local/session storage.")
tab_app = typer.Typer(help="Manage tabs.")
window_app = typer.Typer(help="Manage windows.")

app.add_typer(get_app, name="get")
app.add_typer(is_app, name="is")
app.add_typer(cookies_app, name="cookies")
app.add_typer(storage_app, name="storage")
app.add_typer(tab_app, name="tab")
app.add_typer(window_app, name="window")

navigation.register(app)
interaction.register(app)
wait.register(app)
info.register(get_app)
state.register(is_app)
capture.register(app)
evaluate.register(app)
storage.register(cookies_app, storage_app)
tabs.register(tab_app, window_app)
snapshot.register(app)
misc.register(app)
captcha.register(app)


if __name__ == "__main__":
    app()
