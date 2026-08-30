"""Shared pytest fixtures.

Every test in this suite runs against an isolated ``~/.llm-browser``
state directory rather than the real one, so tests never read or
clobber a developer's actual persistent-session state.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    """Point ``Path.home()`` at a throwaway directory for every test."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path
