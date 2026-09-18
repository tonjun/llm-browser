"""Background process that owns the persistent Chrome session.

SeleniumBase ties a spawned Chrome process's lifetime to the Python
process that launched it (via an ``atexit`` hook), so for the browser
to survive past a single ``llm-browser`` CLI invocation, something has
to stay alive holding the driver. This module is that something: it
launches Chrome once, records how to reach it in the state directory
(see :mod:`llm_browser.session`), and then blocks until asked to stop.

It is spawned detached (new session/process group) by
:func:`llm_browser.browser.open_url` and is not meant to be run
directly by users - see the ``llm-browser close`` command for
shutting it down.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
import time

from seleniumbase import sb_cdp

from llm_browser import session


def _run(headless: bool, headed: bool) -> None:
    driver = sb_cdp.Chrome(
        headless=headless, headed=headed, user_data_dir=str(session.profile_dir())
    )

    def _shutdown(_signum, _frame) -> None:
        try:
            driver.quit()
        finally:
            session.clear_state()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    port = driver.get_rd_port()
    session.write_state(pid=os.getpid(), host="127.0.0.1", port=port)

    # Block until told to stop (SIGTERM/SIGINT above) - or until Chrome
    # itself goes away (user closed the last window, crash), in which case
    # a plain signal.pause() would leave this process and a stale
    # session.json behind until the next `open` cleaned them up.
    _wait_for_chrome_exit("127.0.0.1", port)
    with contextlib.suppress(Exception):
        driver.quit()
    session.clear_state()


# How often to check that Chrome's debug port is still answering.
_CHROME_POLL_INTERVAL = 2.0


def _wait_for_chrome_exit(host: str, port: int) -> None:
    """Return once Chrome's CDP port stops accepting connections."""
    while session._port_open(host, port):
        time.sleep(_CHROME_POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="llm-browser persistent session daemon"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--headless", action="store_true")
    group.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    _run(headless=args.headless, headed=args.headed)


if __name__ == "__main__":
    main()
