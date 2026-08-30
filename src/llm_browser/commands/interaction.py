"""Interaction commands: click, type, fill, drag, scroll, and related actions."""

from __future__ import annotations

import typer

from llm_browser.browser import gui, interaction


def register(app: typer.Typer) -> None:
    @app.command()
    def click(
        selector: str = typer.Argument(None, help="CSS selector or @eN ref."),
        text: str = typer.Option(
            None, "--text", help="Click the first element matching this text instead."
        ),
        gui_: bool = typer.Option(
            False,
            "--gui",
            help="Click via real OS pointer (PyAutoGUI); needs --headed.",
        ),
    ) -> None:
        """Click an element."""
        if gui_:
            if not selector:
                raise typer.BadParameter("--gui requires a selector.")
            gui.gui_click(selector)
            return
        interaction.click(selector=selector, text=text)

    @app.command()
    def dblclick(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Double-click an element."""
        interaction.dblclick(selector)

    @app.command(name="type")
    def type_(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        text: str = typer.Argument(..., help="Text to type (does not clear first)."),
    ) -> None:
        """Type into an element without clearing it first."""
        interaction.type_text(selector, text)

    @app.command()
    def fill(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        text: str = typer.Argument(..., help="Text to fill in."),
    ) -> None:
        """Clear an element and type into it."""
        interaction.fill(selector, text)

    @app.command()
    def press(
        key: str = typer.Argument(
            ..., help="Key or combination, e.g. Enter, Control+a."
        ),
        selector: str = typer.Option(
            None,
            "--selector",
            help="Element to send the key to (default: focused element).",
        ),
    ) -> None:
        """Press a key."""
        interaction.press(key, selector=selector)

    @app.command()
    def hover(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        gui_: bool = typer.Option(
            False,
            "--gui",
            help="Hover via real OS pointer (PyAutoGUI); needs --headed.",
        ),
    ) -> None:
        """Hover over an element."""
        if gui_:
            # No dedicated gui hover-only helper is exposed; hover-and-click
            # to the same selector is the closest primitive, so route plain
            # hover through the CDP path unless the user really wants a
            # hover+click gesture via `gui-hover-click`.
            raise typer.BadParameter(
                "Use `gui-hover-click` for GUI-driven hover+click."
            )
        interaction.hover(selector)

    @app.command()
    def focus(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Focus an element."""
        interaction.focus(selector)

    @app.command()
    def check(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Check a checkbox."""
        interaction.check(selector)

    @app.command()
    def uncheck(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Uncheck a checkbox."""
        interaction.uncheck(selector)

    @app.command()
    def select(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        values: list[str] = typer.Argument(
            ..., help="One or more option values to select."
        ),
    ) -> None:
        """Select dropdown option(s) by value."""
        interaction.select_option(selector, values)

    @app.command()
    def drag(
        src: str = typer.Argument(..., help="Source CSS selector or @eN ref."),
        dst: str = typer.Argument(..., help="Destination CSS selector or @eN ref."),
        gui_: bool = typer.Option(
            False, "--gui", help="Drag via real OS pointer (PyAutoGUI); needs --headed."
        ),
    ) -> None:
        """Drag and drop."""
        if gui_:
            gui.gui_drag(src, dst)
            return
        interaction.drag(src, dst)

    @app.command()
    def upload(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
        files: list[str] = typer.Argument(..., help="File path(s) to upload."),
    ) -> None:
        """Upload file(s) to a file input."""
        interaction.upload(selector, files)

    @app.command()
    def scroll(
        direction: str = typer.Argument(
            "down", help="up, down, left, right, top, or bottom."
        ),
        px: int = typer.Argument(
            300, help="Pixels to scroll (ignored for top/bottom)."
        ),
        until_count: int = typer.Option(
            None,
            "--until-count",
            help="Keep scrolling down until --selector matches this many "
            "elements, growth stalls, or --timeout elapses.",
        ),
        selector: str = typer.Option(
            None,
            "--selector",
            help="Element selector to count (required with --until-count).",
        ),
        timeout: float = typer.Option(
            25.0, "--timeout", help="Max seconds for --until-count."
        ),
    ) -> None:
        """Scroll the page."""
        if until_count is not None:
            if not selector:
                raise typer.BadParameter("--until-count requires --selector.")
            print(
                interaction.scroll_until_count(
                    selector, until_count, px=px, timeout=timeout
                )
            )
            return
        if direction == "top":
            interaction.scroll_to_top()
        elif direction == "bottom":
            interaction.scroll_to_bottom()
        else:
            interaction.scroll(direction, px)

    @app.command()
    def scrollintoview(
        selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    ) -> None:
        """Scroll an element into view."""
        interaction.scroll_into_view(selector)
