"""Typer CLI entrypoint for llm-browser.

Command surface modeled on agent-browser's CLI (see
``docs/agent-browser/`` for the original) but implemented purely with
what SeleniumBase's CDP-mode API exposes - see ``docs/commands.md``
for the full reference, including what's *not* supported and why.
"""

from __future__ import annotations

import json as json_module
import sys
from typing import Any

import typer

from llm_browser import browser

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


def _print(result: Any) -> None:
    if result is None:
        return
    if isinstance(result, str):
        print(result)
    else:
        print(json_module.dumps(result, indent=2, default=str))


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------


@app.command()
def open(
    url: str = typer.Argument(..., help="URL to open."),
    headless: bool = typer.Option(False, "--headless", help="Run the browser headlessly."),
) -> None:
    """Open URL in a SeleniumBase CDP Mode browser session.

    The browser session is persistent: the first call starts a
    background browser and leaves it running; later calls reuse it.
    """
    browser.open_url(url, headless=headless)


@app.command()
def close() -> None:
    """Close the persistent browser session, if one is running."""
    if browser.close_session():
        print("Session closed.")
    else:
        print("No running session.")


@app.command()
def back() -> None:
    """Go back."""
    browser.go_back()


@app.command()
def forward() -> None:
    """Go forward."""
    browser.go_forward()


@app.command()
def reload(
    ignore_cache: bool = typer.Option(False, "--ignore-cache", help="Bypass the cache on reload."),
) -> None:
    """Reload the current page."""
    browser.reload_page(ignore_cache=ignore_cache)


# --------------------------------------------------------------------------
# Interaction
# --------------------------------------------------------------------------


@app.command()
def click(
    selector: str = typer.Argument(None, help="CSS selector or @eN ref."),
    text: str = typer.Option(None, "--text", help="Click the first element matching this text instead."),
    gui: bool = typer.Option(False, "--gui", help="Click via real OS pointer (PyAutoGUI); needs --headed."),
) -> None:
    """Click an element."""
    if gui:
        if not selector:
            raise typer.BadParameter("--gui requires a selector.")
        browser.gui_click(selector)
        return
    browser.click(selector=selector, text=text)


@app.command()
def dblclick(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Double-click an element."""
    browser.dblclick(selector)


@app.command(name="type")
def type_(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    text: str = typer.Argument(..., help="Text to type (does not clear first)."),
) -> None:
    """Type into an element without clearing it first."""
    browser.type_text(selector, text)


@app.command()
def fill(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    text: str = typer.Argument(..., help="Text to fill in."),
) -> None:
    """Clear an element and type into it."""
    browser.fill(selector, text)


@app.command()
def press(
    key: str = typer.Argument(..., help="Key or combination, e.g. Enter, Control+a."),
    selector: str = typer.Option(None, "--selector", help="Element to send the key to (default: focused element)."),
) -> None:
    """Press a key."""
    browser.press(key, selector=selector)


@app.command()
def hover(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    gui: bool = typer.Option(False, "--gui", help="Hover via real OS pointer (PyAutoGUI); needs --headed."),
) -> None:
    """Hover over an element."""
    if gui:
        # No dedicated gui hover-only helper is exposed; hover-and-click
        # to the same selector is the closest primitive, so route plain
        # hover through the CDP path unless the user really wants a
        # hover+click gesture via `gui-hover-click`.
        raise typer.BadParameter("Use `gui-hover-click` for GUI-driven hover+click.")
    browser.hover(selector)


@app.command()
def focus(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Focus an element."""
    browser.focus(selector)


@app.command()
def check(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Check a checkbox."""
    browser.check(selector)


@app.command()
def uncheck(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Uncheck a checkbox."""
    browser.uncheck(selector)


@app.command()
def select(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    values: list[str] = typer.Argument(..., help="One or more option values to select."),
) -> None:
    """Select dropdown option(s) by value."""
    browser.select_option(selector, values)


@app.command()
def drag(
    src: str = typer.Argument(..., help="Source CSS selector or @eN ref."),
    dst: str = typer.Argument(..., help="Destination CSS selector or @eN ref."),
    gui: bool = typer.Option(False, "--gui", help="Drag via real OS pointer (PyAutoGUI); needs --headed."),
) -> None:
    """Drag and drop."""
    if gui:
        browser.gui_drag(src, dst)
        return
    browser.drag(src, dst)


@app.command()
def upload(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    files: list[str] = typer.Argument(..., help="File path(s) to upload."),
) -> None:
    """Upload file(s) to a file input."""
    browser.upload(selector, files)


@app.command()
def scroll(
    direction: str = typer.Argument("down", help="up, down, left, right, top, or bottom."),
    px: int = typer.Argument(300, help="Pixels to scroll (ignored for top/bottom)."),
) -> None:
    """Scroll the page."""
    if direction == "top":
        browser.scroll_to_top()
    elif direction == "bottom":
        browser.scroll_to_bottom()
    else:
        browser.scroll(direction, px)


@app.command()
def scrollintoview(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Scroll an element into view."""
    browser.scroll_into_view(selector)


# --------------------------------------------------------------------------
# Wait
# --------------------------------------------------------------------------


@app.command()
def wait(
    selector: str = typer.Argument(None, help="Wait for this element (CSS selector or @eN ref)."),
    ms: int = typer.Option(None, "--ms", help="Wait this many milliseconds instead."),
    text: str = typer.Option(None, "--text", help="Wait for this text to appear on the page."),
    url: str = typer.Option(None, "--url", help="Wait for the current URL to match this glob pattern."),
    fn: str = typer.Option(None, "--fn", help="Wait for this JS expression to become truthy."),
    timeout: float = typer.Option(25.0, "--timeout", help="Timeout in seconds."),
) -> None:
    """Wait for an element, text, URL, timeout, or JS condition."""
    browser.wait_for(selector=selector, ms=ms, text=text, url=url, js_fn=fn, timeout=timeout)


# --------------------------------------------------------------------------
# Get info
# --------------------------------------------------------------------------


@get_app.command("text")
def get_text(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Get an element's visible text."""
    _print(browser.get_text(selector))


@get_app.command("html")
def get_html(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Get an element's innerHTML."""
    _print(browser.get_html(selector))


@get_app.command("value")
def get_value(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Get an input's value."""
    _print(browser.get_value(selector))


@get_app.command("attr")
def get_attr(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    name: str = typer.Argument(..., help="Attribute name."),
) -> None:
    """Get an element's attribute."""
    _print(browser.get_attr(selector, name))


@get_app.command("title")
def get_title() -> None:
    """Get the page title."""
    _print(browser.get_title())


@get_app.command("url")
def get_url() -> None:
    """Get the current URL."""
    _print(browser.get_url())


@get_app.command("count")
def get_count(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Count matching elements."""
    _print(browser.get_count(selector))


@get_app.command("box")
def get_box(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Get an element's bounding box."""
    _print(browser.get_box(selector))


@get_app.command("styles")
def get_styles(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref."),
    prop: str = typer.Option(None, "--prop", help="Only this computed style property."),
) -> None:
    """Get an element's computed styles."""
    _print(browser.get_styles(selector, prop=prop))


@get_app.command("cdp-url")
def get_cdp_url() -> None:
    """Get the CDP WebSocket URL."""
    _print(browser.get_cdp_url())


# --------------------------------------------------------------------------
# Check state
# --------------------------------------------------------------------------


@is_app.command("visible")
def is_visible(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Check whether an element is visible."""
    _print(browser.is_visible(selector))


@is_app.command("enabled")
def is_enabled(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Check whether an element is enabled."""
    _print(browser.is_enabled(selector))


@is_app.command("checked")
def is_checked(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Check whether a checkbox is checked."""
    _print(browser.is_checked(selector))


@is_app.command("online")
def is_online() -> None:
    """Check whether the browser has network connectivity."""
    _print(browser.is_online())


# --------------------------------------------------------------------------
# Screenshots & PDF
# --------------------------------------------------------------------------


@app.command()
def screenshot(path: str = typer.Argument(None, help="Output path (default: a generated path).")) -> None:
    """Take a screenshot (viewport only - see docs/commands.md for the --full caveat)."""
    print(browser.screenshot(path))


@app.command()
def pdf(path: str = typer.Argument(..., help="Output path.")) -> None:
    """Save the current page as a PDF."""
    print(browser.save_pdf(path))


# --------------------------------------------------------------------------
# Eval
# --------------------------------------------------------------------------


@app.command()
def eval(
    js: str = typer.Argument(None, help="JavaScript to evaluate."),
    stdin: bool = typer.Option(False, "--stdin", help="Read the script from stdin instead."),
) -> None:
    """Evaluate JavaScript in the page."""
    script = sys.stdin.read() if stdin else js
    if not script:
        raise typer.BadParameter("Provide a script argument or use --stdin.")
    _print(browser.evaluate(script))


# --------------------------------------------------------------------------
# Cookies & storage
# --------------------------------------------------------------------------


@cookies_app.command("get")
def cookies_get() -> None:
    """Get all cookies."""
    _print(browser.cookies_get())


@cookies_app.command("set")
def cookies_set(
    name: str = typer.Argument(..., help="Cookie name."),
    value: str = typer.Argument(..., help="Cookie value."),
) -> None:
    """Set a cookie."""
    browser.cookies_set(name, value)


@cookies_app.command("clear")
def cookies_clear() -> None:
    """Clear all cookies."""
    browser.cookies_clear()


@storage_app.command("get")
def storage_get(
    key: str = typer.Argument(None, help="Key to read (omit for all keys)."),
    session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
) -> None:
    """Get a storage value, or all of storage if no key is given."""
    _print(browser.storage_get(key=key, use_session=session_storage))


@storage_app.command("set")
def storage_set(
    key: str = typer.Argument(..., help="Key to write."),
    value: str = typer.Argument(..., help="Value to write."),
    session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
) -> None:
    """Set a storage value."""
    browser.storage_set(key, value, use_session=session_storage)


@storage_app.command("clear")
def storage_clear(
    session_storage: bool = typer.Option(False, "--session-storage", help="Use sessionStorage instead of localStorage."),
) -> None:
    """Clear storage."""
    browser.storage_clear(use_session=session_storage)


# --------------------------------------------------------------------------
# Tabs & windows
# --------------------------------------------------------------------------


@tab_app.command("new")
def tab_new(url: str = typer.Argument(None, help="URL to open in the new tab.")) -> None:
    """Open a new tab."""
    browser.tab_new(url)


@tab_app.command("list")
def tab_list() -> None:
    """List open tabs."""
    _print(browser.tab_list())


@tab_app.command("switch")
def tab_switch(index: int = typer.Argument(..., help="Tab index from `tab list` (or -1 for newest).")) -> None:
    """Switch to a tab by index."""
    browser.tab_switch(index)


@tab_app.command("close")
def tab_close(index: int = typer.Argument(None, help="Tab index to close (default: current tab).")) -> None:
    """Close a tab."""
    browser.tab_close(index)


@window_app.command("new")
def window_new(url: str = typer.Argument(None, help="URL to open in the new window.")) -> None:
    """Open a new window."""
    browser.window_new(url)


# --------------------------------------------------------------------------
# Snapshot & refs
# --------------------------------------------------------------------------


@app.command()
def snapshot(
    interactive: bool = typer.Option(False, "-i", "--interactive", help="Only interactive elements."),
    compact: bool = typer.Option(False, "-c", "--compact", help="Remove empty structural nodes."),
    depth: int = typer.Option(None, "-d", "--depth", help="Limit tree depth."),
    selector: str = typer.Option(None, "-s", "--selector", help="Scope to a CSS selector."),
    with_urls: bool = typer.Option(False, "-u", "--urls", help="Include href URLs on links."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Accessibility-tree snapshot with @eN refs for use with other commands.

    See docs/snapshot-and-refs.md for how refs work and their caveats
    (staleness on navigation, no cross-origin iframe inlining).
    """
    print(
        browser.snapshot(
            interactive=interactive,
            compact=compact,
            depth=depth,
            selector=selector,
            with_urls=with_urls,
            as_json=as_json,
        )
    )


# --------------------------------------------------------------------------
# Misc quick wins
# --------------------------------------------------------------------------


@app.command()
def highlight(selector: str = typer.Argument(..., help="CSS selector or @eN ref.")) -> None:
    """Highlight an element."""
    browser.highlight(selector)


@app.command()
def read(selector: str = typer.Argument(None, help="Only this subtree (CSS selector).")) -> None:
    """Read the current page as plain text."""
    print(browser.read_page(selector))


@app.command(name="internalize-links")
def internalize_links() -> None:
    """Rewrite target="_blank" links to open in the same tab."""
    browser.internalize_links()


@app.command(name="tile-windows")
def tile_windows() -> None:
    """Tile open browser windows."""
    browser.tile_windows()


@app.command(name="mfa-code")
def mfa_code_cmd(totp_key: str = typer.Argument(None, help="TOTP secret key (or configured default).")) -> None:
    """Generate a TOTP code for 2FA."""
    _print(browser.mfa_code(totp_key))


@app.command(name="enter-mfa")
def enter_mfa(
    selector: str = typer.Argument(..., help="CSS selector or @eN ref for the code field."),
    totp_key: str = typer.Argument(None, help="TOTP secret key (or configured default)."),
) -> None:
    """Generate and enter a TOTP code into a field."""
    browser.enter_mfa(selector, totp_key)


@app.command(name="gui-hover-click")
def gui_hover_click(
    hover_selector: str = typer.Argument(..., help="Element to hover over first."),
    click_selector: str = typer.Argument(..., help="Element to click after hovering."),
) -> None:
    """Hover then click via the real OS pointer (PyAutoGUI); needs --headed."""
    browser.gui_hover_and_click(hover_selector, click_selector)


# --------------------------------------------------------------------------
# Captcha solving
# --------------------------------------------------------------------------


@app.command(name="solve-captcha")
@app.command(name="click-captcha")
def solve_captcha(
    gui: bool = typer.Option(
        False, "--gui", help="Solve via real OS pointer (PyAutoGUI) instead of CDP; needs --headed."
    ),
) -> None:
    """Auto-detect and solve/click past a supported captcha on the page.

    Supports Cloudflare Turnstile, Google reCAPTCHA v2 checkbox,
    hCaptcha, DataDome sliders, and Friendly Captcha. Best-effort and
    markup-shape-dependent - see docs/commands.md for the full caveat.
    """
    result = browser.solve_captcha(gui=gui)
    # `solve_captcha()`/`click_captcha()` return None regardless of
    # outcome (SeleniumBase discards the inner True/False); only
    # `gui_click_captcha()` reliably returns False for "nothing
    # detected". Treat both as "can't confirm a captcha was solved"
    # rather than claiming success either way.
    if result in (False, None):
        print("No supported captcha detected on this page (or nothing to confirm).")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
