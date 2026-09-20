"""Tests for llm_browser.browser.post."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from llm_browser.browser import post


def _driver(monkeypatch, url, generic=None, adapter=None):
    """Driver whose evaluate() returns ``generic`` for the generic extractor
    and ``adapter`` for any site-specific one (as JSON strings, like the
    real extractors)."""
    driver = MagicMock()
    driver.get_current_url.return_value = url

    def evaluate(js):
        payload = generic if js == post._GENERIC_JS else adapter
        return json.dumps(payload)

    driver.evaluate.side_effect = evaluate
    monkeypatch.setattr(post, "with_driver", lambda fn: fn(driver))
    monkeypatch.setattr(post.time, "sleep", lambda s: None)
    return driver


def _run(**kwargs):
    return json.loads(post.extract_post(**kwargs))


class TestAdapterFor:
    @pytest.mark.parametrize(
        "url,platform,marker",
        [
            ("https://old.reddit.com/r/a/comments/1/x/", "reddit", ".thing.link"),
            ("https://www.reddit.com/r/a/comments/1/x/", "reddit", "shreddit-post"),
            ("https://reddit.com/r/a/", "reddit", "shreddit-post"),
            ("https://x.com/u/status/1", "x", "tweet"),
            ("https://twitter.com/u/status/1", "x", "tweet"),
            ("https://mobile.twitter.com/u/status/1", "x", "tweet"),
            ("https://news.ycombinator.com/item?id=1", "hackernews", "fatitem"),
            ("https://www.facebook.com/u/posts/1", "facebook", "role="),
            ("https://m.facebook.com/u/posts/1", "facebook", "role="),
            ("https://www.instagram.com/p/abc/", "instagram", "og:description"),
            (
                "https://nz.trustpilot.com/review/shopee.ph",
                "trustpilot",
                "__NEXT_DATA__",
            ),
            ("https://www.trustpilot.com/reviews/abc", "trustpilot", "__NEXT_DATA__"),
            ("https://trustpilot.com/review/x.com", "trustpilot", "__NEXT_DATA__"),
            (
                "https://www.g2.com/products/ibm-watsonx-ai/reviews",
                "g2",
                "Review collected by",
            ),
            ("https://g2.com/products/x/reviews?page=2", "g2", "survey_responses"),
            (
                "https://www.threads.com/@openai/post/DVHLaLdErKM",
                "threads",
                "injected_media_ids",
            ),
            ("https://threads.net/@openai/post/DVHLaLdErKM", "threads", "pressable"),
            ("https://www.quora.com/What-is-x", "quora", "dom_annotate"),
            ("https://es.quora.com/Que-es-x", "quora", "dom_annotate"),
            (
                "https://www.linkedin.com/posts/u_x-activity-7326818689821954048-wZ2W/",
                "linkedin",
                "feed-shared-update-v2",
            ),
        ],
    )
    def test_known_hosts(self, url, platform, marker):
        got_platform, js = post._adapter_for(url)
        assert got_platform == platform
        assert js is not None and marker in js

    def test_unknown_host_is_generic(self):
        assert post._adapter_for("https://forum.example.com/t/1") == ("generic", None)

    def test_lookalike_host_is_generic(self):
        assert post._adapter_for("https://notreddit.com/")[0] == "generic"
        assert post._adapter_for("https://nottrustpilot.com/")[0] == "generic"
        assert post._adapter_for("https://notquora.com/")[0] == "generic"
        assert post._adapter_for("https://notg2.com/")[0] == "generic"
        assert post._adapter_for("https://notthreads.com/")[0] == "generic"


class TestNormalizers:
    def test_count(self):
        assert post._count("1,234") == 1234
        assert post._count("12 points") == 12
        assert post._count("1.2k") == 1200
        assert post._count("3M") == 3_000_000
        assert post._count(5) == 5
        assert post._count("no number") is None
        assert post._count(None) is None
        assert post._count(True) is None

    def test_text_preserves_paragraphs(self):
        assert post._text("a   b\n\n\n\nc \n d") == "a b\n\nc\nd"
        assert post._text("   ") is None

    def test_line_collapses_whitespace(self):
        assert post._line("  a \n b ") == "a b"
        assert post._line("") is None

    def test_media_absolutizes_dedupes_and_filters(self):
        media = post._media(
            [
                {"url": "/a.png", "type": "image", "alt": " pic "},
                {"url": "https://x.test/a.png", "type": "image"},
                {"url": "blob:https://x.test/1", "type": "video"},
                {"url": "data:image/png;base64,AAA"},
                {"url": ""},
                {"url": "https://x.test/v.mp4", "type": "video"},
            ],
            "https://x.test/post",
        )
        assert media == [
            {"type": "image", "url": "https://x.test/a.png", "alt": "pic"},
            {"type": "video", "url": "https://x.test/v.mp4", "alt": None},
        ]

    def test_nest_comments_by_depth(self):
        flat = [
            {"depth": 0, "author": "a", "content": "1"},
            {"depth": 1, "author": "b", "content": "1.1"},
            {"depth": 2, "author": "c", "content": "1.1.1"},
            {"depth": 1, "author": "d", "content": "1.2"},
            {"depth": 0, "author": "e", "content": "2"},
        ]
        tree = post._nest_comments(flat, "https://x.test/")
        assert [c["content"] for c in tree] == ["1", "2"]
        first = tree[0]["replies"]
        assert [c["content"] for c in first] == ["1.1", "1.2"]
        assert first[0]["replies"][0]["content"] == "1.1.1"
        assert first[1]["replies"] == []

    def test_nest_comments_drops_empty_and_handles_orphan_depth(self):
        flat = [
            {"depth": 3, "author": "a", "content": "deep first"},
            {"depth": 0, "author": None, "content": " "},
            {"depth": "bad", "author": "b", "content": "x"},
        ]
        tree = post._nest_comments(flat, "https://x.test/")
        assert [c["content"] for c in tree] == ["deep first", "x"]


class TestMerge:
    def test_adapter_wins_generic_fills_gaps(self):
        merged = post._merge(
            {"title": "generic", "author": "g", "published": "2024"},
            {"title": "adapter", "author": None},
        )
        assert merged == {"title": "adapter", "author": "g", "published": "2024"}

    def test_empty_string_is_a_deliberate_override(self):
        assert post._merge({"title": "X user on X"}, {"title": ""})["title"] == ""

    def test_adapter_lists_are_authoritative_even_when_empty(self):
        merged = post._merge(
            {"media": [{"url": "u"}], "comments": [{"content": "c"}]},
            {"media": [], "comments": []},
        )
        assert merged["media"] == [] and merged["comments"] == []

    def test_adapter_none_lists_fall_back_to_generic(self):
        merged = post._merge(
            {"media": [{"url": "u"}], "comments": [{"content": "c"}]},
            {"media": None, "comments": None},
        )
        assert merged["media"] == [{"url": "u"}]
        assert merged["comments"] == [{"content": "c"}]


class TestExtractPost:
    def test_generic_page(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://forum.example.com/t/1",
            generic={
                "title": " My  thread ",
                "author": {"name": "alice", "url": "/u/alice"},
                "published": "2024-01-02T03:04:05Z",
                "content": "Body\n\n\n\ntext",
                "score": "7",
                "media": [{"type": "image", "url": "/i.png"}],
                "comments": [
                    {"depth": 0, "author": {"name": "bob"}, "content": "hi"},
                    {"depth": 1, "author": {"name": "carol"}, "content": "yo"},
                ],
            },
        )
        result = _run()
        assert result["platform"] == "generic"
        assert result["url"] == "https://forum.example.com/t/1"
        assert result["title"] == "My thread"
        assert result["author"] == {
            "name": "alice",
            "handle": None,
            "url": "https://forum.example.com/u/alice",
        }
        assert result["content"] == "Body\n\ntext"
        assert result["score"] == 7
        assert result["comment_count"] == 2  # inferred from extracted comments
        assert result["media"][0]["url"] == "https://forum.example.com/i.png"
        assert result["comments"][0]["replies"][0]["content"] == "yo"

    def test_all_schema_keys_present_when_empty(self, monkeypatch):
        _driver(monkeypatch, "https://example.com/", generic={"title": "T"})
        result = _run()
        assert set(result) == {
            "url",
            "platform",
            "title",
            "author",
            "published",
            "content",
            "score",
            "comment_count",
            "media",
            "comments",
        }
        assert result["author"] is None
        assert result["media"] == [] and result["comments"] == []

    def test_adapter_overrides_generic(self, monkeypatch):
        driver = _driver(
            monkeypatch,
            "https://news.ycombinator.com/item?id=1",
            generic={"title": "generic title", "published": "gen-date"},
            adapter={
                "title": "HN title",
                "content": "text",
                "comment_count": "12 comments",
                "comments": [{"depth": 0, "author": "x", "content": "c"}],
            },
        )
        result = _run()
        assert result["platform"] == "hackernews"
        assert result["title"] == "HN title"
        assert result["published"] == "gen-date"
        assert result["comment_count"] == 12
        assert driver.evaluate.call_count == 2

    def test_unknown_host_tries_discourse_detection(self, monkeypatch):
        driver = _driver(
            monkeypatch,
            "https://forum.example.com/t/topic/1",
            generic={"title": "generic title"},
            adapter={
                "title": "Topic",
                "content": "first post",
                "comments": [{"depth": 0, "author": "bob", "content": "reply"}],
            },
        )
        result = _run()
        assert result["platform"] == "discourse"
        assert result["title"] == "Topic"
        assert result["comments"][0]["content"] == "reply"
        assert "generator" in driver.evaluate.call_args.args[0]

    def test_discourse_detection_miss_stays_generic(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://forum.example.com/t/1",
            generic={"title": "T"},
            adapter=None,
        )
        assert _run()["platform"] == "generic"

    def test_linkedin_adapter_overrides_page_title_and_nests_replies(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://www.linkedin.com/posts/u_x-activity-7326818689821954048-wZ2W/",
            generic={"title": "(23) Post | LinkedIn", "content": "Feed detail update"},
            adapter={
                "title": "",
                "author": {
                    "name": "Rajiv Nair",
                    "url": "https://www.linkedin.com/in/r",
                },
                "published": "2025-05-10T04:01:41.362Z",
                "content": "post text",
                "score": "44",
                "comment_count": "2 comments",
                "comments": [
                    {"depth": 0, "author": {"name": "a"}, "content": "top"},
                    {"depth": 1, "author": {"name": "b"}, "content": "reply"},
                ],
            },
        )
        result = _run()
        assert result["platform"] == "linkedin"
        assert result["title"] is None
        assert result["content"] == "post text"
        assert (result["score"], result["comment_count"]) == (44, 2)
        assert result["comments"][0]["replies"][0]["content"] == "reply"

    def test_trustpilot_business_page_overrides_generic_junk(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://nz.trustpilot.com/review/shopee.ph?page=2",
            generic={
                "title": 'Shopee is rated "Bad" with 1.4 / 5 on Trustpilot',
                "published": "2026-09-10T19:51:19.000Z",
                "content": "nav chrome",
            },
            adapter={
                "title": "Shopee (shopee.ph) reviews",
                "author": "",
                "published": "",
                "score": "",
                "content": "TrustScore 1.4/5 - 334 reviews\nShowing page 2 of 16",
                "comment_count": 334,
                "comments": [
                    {
                        "depth": 0,
                        "author": {"name": "a"},
                        "content": "[1/5] t\n\nbody",
                        "score": 1,
                    },
                    {"depth": 1, "author": {"name": "Shopee"}, "content": "our reply"},
                ],
            },
        )
        result = _run()
        assert result["platform"] == "trustpilot"
        assert result["title"] == "Shopee (shopee.ph) reviews"
        assert result["author"] is None and result["published"] is None
        assert result["score"] is None
        assert result["comment_count"] == 334
        review = result["comments"][0]
        assert review["score"] == 1
        assert review["replies"][0]["content"] == "our reply"

    def test_g2_product_page_lists_reviews_as_comments(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://www.g2.com/products/ibm-watsonx-ai/reviews",
            generic={"title": "The G2 on IBM watsonx.ai", "content": "nav chrome"},
            adapter={
                "title": "IBM watsonx.ai reviews",
                "author": "",
                "published": "",
                "score": "",
                "content": "G2 rating 4.4/5 - 153 reviews\nShowing page 1 of 16",
                "comment_count": 153,
                "media": [],
                "comments": [
                    {
                        "depth": 0,
                        "author": {"name": "Manan S.", "url": "/users/1"},
                        "published": "2026-07-29T16:53:48-05:00",
                        "content": "[4/5] Great\n\nWhat do you like best?\n\nEverything",
                        "url": "/survey_responses/ibm-watsonx-ai-review-1",
                    },
                ],
            },
        )
        result = _run()
        assert result["platform"] == "g2"
        assert result["title"] == "IBM watsonx.ai reviews"
        assert result["author"] is None and result["published"] is None
        assert result["comment_count"] == 153
        review = result["comments"][0]
        assert review["content"].startswith("[4/5] Great")
        assert review["author"]["url"] == "https://www.g2.com/users/1"
        assert review["url"] == (
            "https://www.g2.com/survey_responses/ibm-watsonx-ai-review-1"
        )

    def test_threads_thread_page_overrides_generic_login_junk(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://www.threads.com/@openai/post/DVHLaLdErKM",
            generic={
                "title": "Threads \u2022 Log in",
                "content": "Join Threads to share ideas",
            },
            adapter={
                "title": "",
                "author": {
                    "name": "openai",
                    "handle": "@openai",
                    "url": "/@openai",
                },
                "published": "2026-02-23T19:28:21.000Z",
                "content": "Last week, Sam got to meet...",
                "score": "1K",
                "comment_count": "61",
                "media": [],
                "comments": [
                    {
                        "depth": 0,
                        "author": {"name": "a"},
                        "content": "Wow",
                        "score": "1",
                    },
                    {"depth": 0, "author": {"name": "b"}, "content": "Nice"},
                ],
            },
        )
        result = _run()
        assert result["platform"] == "threads"
        assert result["title"] is None
        assert result["author"]["url"] == "https://www.threads.com/@openai"
        assert (result["score"], result["comment_count"]) == (1000, 61)
        assert [c["content"] for c in result["comments"]] == ["Wow", "Nice"]

    def test_rereads_while_adapter_reports_pending(self, monkeypatch):
        """Quora's adapter clicks "(more)" and reports pending=True; the next
        read sees the expanded text."""
        driver = MagicMock()
        driver.get_current_url.return_value = "https://www.quora.com/What-is-x"
        answers = iter(
            [
                {
                    "title": "Q",
                    "pending": True,
                    "comments": [{"author": "a", "content": "short ... (more)"}],
                },
                {
                    "title": "Q",
                    "pending": False,
                    "comments": [{"author": "a", "content": "the full answer"}],
                },
            ]
        )

        def evaluate(js):
            if js == post._GENERIC_JS:
                return json.dumps({"title": "generic"})
            return json.dumps(next(answers))

        driver.evaluate.side_effect = evaluate
        monkeypatch.setattr(post, "with_driver", lambda fn: fn(driver))
        monkeypatch.setattr(post.time, "sleep", lambda s: None)
        result = _run()
        assert result["platform"] == "quora"
        assert result["comments"][0]["content"] == "the full answer"
        assert "pending" not in result

    def test_pending_forever_gives_up_without_hint(self, monkeypatch, capsys):
        _driver(
            monkeypatch,
            "https://www.quora.com/What-is-x",
            generic={"title": "generic"},
            adapter={
                "title": "Q",
                "pending": True,
                "comments": [{"author": "a", "content": "c ... (more)"}],
            },
        )
        ticks = iter([0.0, 5.0, 11.0])
        monkeypatch.setattr(post.time, "monotonic", lambda: next(ticks))
        result = _run()
        assert result["title"] == "Q"
        assert result["comments"][0]["content"] == "c ... (more)"
        assert capsys.readouterr().err == ""

    def test_empty_title_override_drops_generic_title(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://x.com/u/status/1",
            generic={"title": 'u on X: "hello"'},
            adapter={"title": "", "content": "hello"},
        )
        result = _run()
        assert result["title"] is None
        assert result["content"] == "hello"

    def test_no_comments_flag(self, monkeypatch):
        _driver(
            monkeypatch,
            "https://example.com/",
            generic={
                "title": "T",
                "comment_count": 40,
                "comments": [{"depth": 0, "author": "a", "content": "c"}],
            },
        )
        result = _run(include_comments=False)
        assert result["comments"] == []
        assert result["comment_count"] == 40

    def test_max_comments_truncates_in_document_order(self, monkeypatch):
        comments = [
            {"depth": 0, "author": "a", "content": "1"},
            {"depth": 1, "author": "b", "content": "1.1"},
            {"depth": 0, "author": "c", "content": "2"},
        ]
        _driver(
            monkeypatch,
            "https://example.com/",
            generic={"title": "T", "comments": comments},
        )
        result = _run(max_comments=2)
        assert len(result["comments"]) == 1
        assert result["comments"][0]["replies"][0]["content"] == "1.1"
        assert result["comment_count"] == 3

    def test_polls_until_adapter_matches(self, monkeypatch):
        driver = MagicMock()
        driver.get_current_url.return_value = "https://old.reddit.com/r/a/comments/1/"
        results = iter([None, None, {"title": "Loaded", "content": "body"}])

        def evaluate(js):
            if js == post._GENERIC_JS:
                return json.dumps({"title": "generic"})
            return json.dumps(next(results))

        driver.evaluate.side_effect = evaluate
        monkeypatch.setattr(post, "with_driver", lambda fn: fn(driver))
        monkeypatch.setattr(post.time, "sleep", lambda s: None)
        result = _run()
        assert result["title"] == "Loaded"
        assert driver.evaluate.call_count == 6  # 3 polls x (generic + adapter)

    def test_gives_up_with_hint_when_nothing_found(self, monkeypatch, capsys):
        _driver(monkeypatch, "https://www.instagram.com/p/x/", generic={}, adapter=None)
        ticks = iter([0.0, 5.0, 11.0, 12.0])
        monkeypatch.setattr(post.time, "monotonic", lambda: next(ticks))
        result = _run()
        assert result["title"] is None and result["content"] is None
        assert result["comments"] == []
        assert "No post found" in capsys.readouterr().err

    def test_tolerates_non_json_extractor_output(self, monkeypatch, capsys):
        driver = MagicMock()
        driver.get_current_url.return_value = "https://example.com/"
        driver.evaluate.return_value = "not json"
        monkeypatch.setattr(post, "with_driver", lambda fn: fn(driver))
        monkeypatch.setattr(post.time, "sleep", lambda s: None)
        ticks = iter([0.0, 11.0])
        monkeypatch.setattr(post.time, "monotonic", lambda: next(ticks))
        result = _run()
        assert result["title"] is None
        assert "No post found" in capsys.readouterr().err
