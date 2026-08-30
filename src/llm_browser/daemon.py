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
import os
import signal
import sys

from seleniumbase import sb_cdp

from llm_browser import session


def _run(headless: bool) -> None:
    driver = sb_cdp.Chrome(headless=headless, user_data_dir=str(session.profile_dir()))

    def _shutdown(_signum, _frame) -> None:  # noqa: ANN001 - signal handler signature
        try:
            driver.quit()
        finally:
            session.clear_state()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    port = driver.get_rd_port()
    session.write_state(pid=os.getpid(), host="127.0.0.1", port=port)

    signal.pause()


def main() -> None:
    parser = argparse.ArgumentParser(description="llm-browser persistent session daemon")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    _run(headless=args.headless)


if __name__ == "__main__":
    main()
