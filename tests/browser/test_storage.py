"""Tests for llm_browser.browser.storage: cookies & local/session storage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_browser.browser import storage


@pytest.fixture
def d(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(storage, "with_driver", lambda fn: fn(driver))
    return driver


class TestCookiesGet:
    def test_returns_empty_list_when_none(self, d):
        d.get_all_cookies.return_value = None
        assert storage.cookies_get() == []

    def test_converts_objects_with_to_json(self, d):
        cookie = MagicMock()
        cookie.to_json.return_value = {"name": "a", "value": "1"}
        d.get_all_cookies.return_value = [cookie]
        assert storage.cookies_get() == [{"name": "a", "value": "1"}]

    def test_passes_through_plain_dicts(self, d):
        d.get_all_cookies.return_value = [{"name": "a", "value": "1"}]
        assert storage.cookies_get() == [{"name": "a", "value": "1"}]


def test_cookies_set_writes_document_cookie(d):
    storage.cookies_set("a", "1")
    js = d.evaluate.call_args.args[0]
    assert '"a"' in js and '"1"' in js
    assert "document.cookie" in js


def test_cookies_clear(d):
    storage.cookies_clear()
    d.clear_cookies.assert_called_once()


class TestStorageGet:
    def test_no_key_reads_local_storage(self, d):
        d.evaluate.return_value = '{"a": "1"}'
        assert storage.storage_get() == {"a": "1"}
        js = d.evaluate.call_args.args[0]
        assert "localStorage" in js

    def test_no_key_reads_session_storage(self, d):
        d.evaluate.return_value = "{}"
        storage.storage_get(use_session=True)
        js = d.evaluate.call_args.args[0]
        assert "sessionStorage" in js

    def test_no_key_empty_result_returns_empty_dict(self, d):
        d.evaluate.return_value = ""
        assert storage.storage_get() == {}

    def test_with_key_local(self, d):
        d.get_local_storage_item.return_value = "v"
        assert storage.storage_get(key="k") == "v"
        d.get_local_storage_item.assert_called_once_with("k")

    def test_with_key_session(self, d):
        d.get_session_storage_item.return_value = "v"
        assert storage.storage_get(key="k", use_session=True) == "v"
        d.get_session_storage_item.assert_called_once_with("k")


class TestStorageSet:
    def test_local(self, d):
        storage.storage_set("k", "v")
        d.set_local_storage_item.assert_called_once_with("k", "v")

    def test_session(self, d):
        storage.storage_set("k", "v", use_session=True)
        d.set_session_storage_item.assert_called_once_with("k", "v")


class TestStorageClear:
    def test_local(self, d):
        storage.storage_clear()
        js = d.evaluate.call_args.args[0]
        assert js == "localStorage.clear()"

    def test_session(self, d):
        storage.storage_clear(use_session=True)
        js = d.evaluate.call_args.args[0]
        assert js == "sessionStorage.clear()"
