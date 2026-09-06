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


def _sent_cmd_dict(d):
    """Decode the CDP wire params from the last d.page.send(...) call."""
    (sent_command,), _ = d.page.send.call_args
    # mycdp commands are generators that yield the CDP wire params.
    return sent_command.send(None)


class TestScreenshot:
    def test_explicit_path_writes_decoded_bytes(self, d, tmp_path):
        d.loop.run_until_complete.return_value = "ZmFrZS1wbmctYnl0ZXM="
        target = tmp_path / "out.png"
        result = capture.screenshot(str(target))
        assert result == str(target)
        assert target.read_bytes() == b"fake-png-bytes"

    def test_no_path_generates_one_under_state_dir(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        result = capture.screenshot(None)
        assert result.startswith(str(session.state_dir()))
        assert result.endswith(".png")

    def test_default_format_sends_png_and_no_quality(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        capture.screenshot(None)
        cmd_dict = _sent_cmd_dict(d)
        assert cmd_dict["params"]["format"] == "png"
        assert "quality" not in cmd_dict["params"]

    def test_jpeg_format_and_quality_forwarded(self, d, tmp_path):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        target = tmp_path / "out.jpg"
        capture.screenshot(str(target), format_="jpeg", quality=40)
        cmd_dict = _sent_cmd_dict(d)
        assert cmd_dict["params"]["format"] == "jpeg"
        assert cmd_dict["params"]["quality"] == 40

    def test_webp_format_and_quality_forwarded(self, d, tmp_path):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        target = tmp_path / "out.webp"
        capture.screenshot(str(target), format_="webp", quality=40)
        cmd_dict = _sent_cmd_dict(d)
        assert cmd_dict["params"]["format"] == "webp"
        assert cmd_dict["params"]["quality"] == 40

    def test_no_path_generates_jpg_extension_for_jpeg_format(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        result = capture.screenshot(None, format_="jpeg", quality=40)
        assert result.endswith(".jpg")

    def test_no_path_generates_webp_extension_for_webp_format(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        result = capture.screenshot(None, format_="webp", quality=40)
        assert result.endswith(".webp")

    def test_full_page_passes_capture_beyond_viewport(self, d, tmp_path):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        target = tmp_path / "out.png"
        capture.screenshot(str(target), full_page=True)
        cmd_dict = _sent_cmd_dict(d)
        assert cmd_dict["params"]["captureBeyondViewport"] is True

    def test_raises_on_empty_capture(self, d):
        d.loop.run_until_complete.return_value = ""
        with pytest.raises(RuntimeError):
            capture.screenshot()

    def test_stdout_returns_data_uri_without_writing_a_file(self, d, tmp_path, monkeypatch):
        d.loop.run_until_complete.return_value = "ZmFrZS1wbmctYnl0ZXM="
        monkeypatch.chdir(tmp_path)
        result = capture.screenshot(to_stdout=True)
        assert result == "data:image/png;base64,ZmFrZS1wbmctYnl0ZXM="
        assert list(tmp_path.iterdir()) == []

    def test_stdout_uses_format_specific_mime_type(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        result = capture.screenshot(to_stdout=True, format_="jpeg", quality=40)
        assert result == "data:image/jpeg;base64,ZmFrZQ=="

    def test_stdout_full_page_passes_capture_beyond_viewport(self, d):
        d.loop.run_until_complete.return_value = "ZmFrZQ=="
        capture.screenshot(to_stdout=True, full_page=True)
        cmd_dict = _sent_cmd_dict(d)
        assert cmd_dict["method"] == "Page.captureScreenshot"
        assert cmd_dict["params"]["format"] == "png"
        assert cmd_dict["params"]["captureBeyondViewport"] is True

    def test_stdout_raises_on_empty_capture(self, d):
        d.loop.run_until_complete.return_value = ""
        with pytest.raises(RuntimeError):
            capture.screenshot(to_stdout=True)


class TestSavePdf:
    def test_splits_path_into_folder_and_name(self, d):
        result = capture.save_pdf("/tmp/docs/report.pdf")
        assert result == "/tmp/docs/report.pdf"
        d.print_to_pdf.assert_called_once_with("report.pdf", folder="/tmp/docs")

    def test_relative_path(self, d):
        result = capture.save_pdf("report.pdf")
        assert result == "report.pdf"
        d.print_to_pdf.assert_called_once_with("report.pdf", folder=".")
