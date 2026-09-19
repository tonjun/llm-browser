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


def test_install_skills_writes_full_inlined_skill_md(tmp_path):
    results = skills.install_skills(tmp_path)
    assert [(r["name"], r["status"]) for r in results] == [("llm-browser", "installed")]
    dest = tmp_path / "llm-browser"
    text = (dest / "SKILL.md").read_text(encoding="utf-8")
    assert text == skills.get_skill("llm-browser", full=True) + "\n"
    assert text.startswith("---\nname: llm-browser")
    assert "--- docs/commands.md ---" in text
    assert [p.name for p in dest.iterdir()] == ["SKILL.md"]
    assert [p.name for p in tmp_path.iterdir()] == ["llm-browser"]


def test_install_skills_skips_existing_without_force(tmp_path):
    (tmp_path / "llm-browser").mkdir()
    (tmp_path / "llm-browser" / "mine.txt").write_text("keep")
    [result] = skills.install_skills(tmp_path)
    assert result["status"] == "skipped"
    assert (tmp_path / "llm-browser" / "mine.txt").read_text() == "keep"
    assert not (tmp_path / "llm-browser" / "SKILL.md").exists()


def test_install_skills_force_replaces_existing_dir(tmp_path):
    (tmp_path / "llm-browser").mkdir()
    (tmp_path / "llm-browser" / "stale.txt").write_text("old")
    [result] = skills.install_skills(tmp_path, force=True)
    assert result["status"] == "installed"
    assert not (tmp_path / "llm-browser" / "stale.txt").exists()
    assert (tmp_path / "llm-browser" / "SKILL.md").is_file()


def test_install_skills_force_over_symlink_leaves_target_alone(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    root = tmp_path / "skills"
    root.mkdir()
    (root / "llm-browser").symlink_to(target)
    skills.install_skills(root, force=True)
    assert (target / "keep.txt").read_text() == "keep"
    assert not (root / "llm-browser").is_symlink()
    assert (root / "llm-browser" / "SKILL.md").is_file()


def test_default_root_user_and_project(tmp_path, monkeypatch):
    # conftest points Path.home() at tmp_path
    assert skills.default_root() == tmp_path / ".claude" / "skills"
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    assert skills.default_root(project=True) == project.resolve() / ".claude" / "skills"
