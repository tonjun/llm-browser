"""Wait command: element, timeout, text, URL, or JS condition."""

from __future__ import annotations

import fnmatch
import time

from seleniumbase.core.sb_cdp import CDPMethods

from llm_browser.browser.core import resolve_selector, with_driver


def wait_for(
    selector: str | None = None,
    ms: int | None = None,
    text: str | None = None,
    url: str | None = None,
    js_fn: str | None = None,
    timeout: float = 25.0,
) -> None:
    def _run(d: CDPMethods) -> None:
        if ms is not None:
            d.sleep(ms / 1000)
            return
        if selector is not None:
            d.wait_for_element(resolve_selector(selector), timeout=timeout)
            return
        if text is not None:
            d.wait_for_text(text, selector="body", timeout=timeout)
            return
        if url is not None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if fnmatch.fnmatch(d.get_current_url(), url):
                    return
                d.sleep(0.2)
            raise TimeoutError(f"Timed out waiting for URL to match {url!r}")
        if js_fn is not None:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if d.evaluate(js_fn):
                    return
                d.sleep(0.2)
            raise TimeoutError(f"Timed out waiting for condition: {js_fn!r}")
        raise ValueError("wait requires one of: selector, ms, text, url, js_fn")

    with_driver(_run)
