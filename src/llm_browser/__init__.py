"""llm_browser package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("llm-browser")
except PackageNotFoundError:
    # Not installed (e.g. running from a raw checkout without `uv sync`).
    __version__ = "0+unknown"
