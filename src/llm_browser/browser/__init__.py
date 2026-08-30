"""SeleniumBase CDP Mode helpers, split into topical submodules.

Browser sessions are persistent: the first ``open`` call spawns a
detached background daemon that owns a Chrome instance, and every
subsequent call reconnects to that same instance over CDP instead of
launching a new browser. See :mod:`llm_browser.daemon` and
:mod:`llm_browser.session` for how that's coordinated, and
``docs/persistent-sessions.md`` for the full design.

``core`` holds the daemon lifecycle (``open_url``/``close_session``)
and the shared attach-call-return plumbing (``with_driver``,
``resolve_selector``); every other module here is a stateless
attach-call-return command grouped by topic (see ``docs/commands.md``
for the user-facing reference and ``docs/snapshot-and-refs.md`` for
the ``@ref`` system specifically).
"""

from __future__ import annotations
