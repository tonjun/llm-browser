"""Cookies & storage sub-apps."""

from __future__ import annotations

import typer

from llm_browser.browser import storage
from llm_browser.commands import _print


def register(cookies_app: typer.Typer, storage_app: typer.Typer) -> None:
    @cookies_app.command("get")
    def cookies_get() -> None:
        """Get all cookies."""
        _print(storage.cookies_get())

    @cookies_app.command("set")
    def cookies_set(
        name: str = typer.Argument(..., help="Cookie name."),
        value: str = typer.Argument(..., help="Cookie value."),
    ) -> None:
        """Set a cookie."""
        storage.cookies_set(name, value)

    @cookies_app.command("clear")
    def cookies_clear() -> None:
        """Clear all cookies."""
        storage.cookies_clear()

    @storage_app.command("get")
    def storage_get(
        key: str = typer.Argument(None, help="Key to read (omit for all keys)."),
        session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
    ) -> None:
        """Get a storage value, or all of storage if no key is given."""
        _print(storage.storage_get(key=key, use_session=session_storage))

    @storage_app.command("set")
    def storage_set(
        key: str = typer.Argument(..., help="Key to write."),
        value: str = typer.Argument(..., help="Value to write."),
        session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
    ) -> None:
        """Set a storage value."""
        storage.storage_set(key, value, use_session=session_storage)

    @storage_app.command("clear")
    def storage_clear(
        session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
    ) -> None:
        """Clear storage."""
        storage.storage_clear(use_session=session_storage)
