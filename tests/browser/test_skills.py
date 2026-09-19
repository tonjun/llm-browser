"""Tests for llm_browser.browser.skills (reads the real bundled skills)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_browser.browser import skills


def test_list_skills_finds_bundled_skills_with_descriptions():
    found = {s["name"]: s["description"] for s in skills.list_skills()}
    assert {"llm-browser", "search-results-extractor"} <= set(found)
    assert all(found.values())


def test_get_skill_returns_skill_md():
    text = skills.get_skill("llm-browser")
    assert text.startswith("---\nname: llm-browser")
    assert "--- docs/" not in text


def test_get_skill_full_appends_docs():
    text = skills.get_skill("llm-browser", full=True)
    assert "--- docs/commands.md ---" in text
    assert "--- docs/snapshot-and-refs.md ---" in text


def test_get_skill_full_without_docs_dir_is_just_skill_md():
    assert skills.get_skill("search-results-extractor", full=True) == (
        skills.get_skill("search-results-extractor")
    )


def test_unknown_skill_lists_available_names():
    with pytest.raises(ValueError, match="unknown skill 'nope'.*llm-browser"):
        skills.get_skill("nope")


def test_skill_path_points_at_directory_with_skill_md():
    assert (Path(skills.skill_path("llm-browser")) / "SKILL.md").is_file()


def test_parse_frontmatter_without_block_is_empty():
    assert skills._parse_frontmatter("# just a heading") == {}
