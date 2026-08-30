"""Tests for llm_browser.browser.capture: screenshots & PDF."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser import session
from llm_browser.browser import capture


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(capture, "with_driver", lambda fn: fn(driver))
    return driver


class TestScreenshot:
    def test_explicit_path_is_split_into_folder_and_name(self, d):
        result = capture.screenshot("/tmp/shots/out.png")
        assert result == "/tmp/shots/out.png"
        d.save_screenshot.assert_called_once_with("out.png", folder="/tmp/shots")

    def test_no_path_generates_one_under_state_dir(self, d):
        result = capture.screenshot(None)
        assert result.startswith(str(session.state_dir()))
        assert result.endswith(".png")
        assert d.save_screenshot.call_args.kwargs["folder"] == str(session.state_dir())

    def test_relative_path_uses_current_dir_as_folder(self, d):
        result = capture.screenshot("out.png")
        assert result == "out.png"
        d.save_screenshot.assert_called_once_with("out.png", folder=".")


class TestSavePdf:
    def test_splits_path_into_folder_and_name(self, d):
        result = capture.save_pdf("/tmp/docs/report.pdf")
        assert result == "/tmp/docs/report.pdf"
        d.print_to_pdf.assert_called_once_with("report.pdf", folder="/tmp/docs")

    def test_relative_path(self, d):
        result = capture.save_pdf("report.pdf")
        assert result == "report.pdf"
        d.print_to_pdf.assert_called_once_with("report.pdf", folder=".")
