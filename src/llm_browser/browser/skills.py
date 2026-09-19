"""Bundled Claude Code skills (``llm_browser/skills/<name>/SKILL.md``).

Pure file reads/copies - no browser or daemon involved. The skills ship
inside the package so they are available to ``uv tool install`` users, not
just repo clones.
"""

from __future__ import annotations

import shutil
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

INSTALLED_SKILL = "llm-browser"  # the only skill `skills install` copies


def _root() -> Traversable:
    return files("llm_browser") / "skills"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Read the flat ``key: value`` lines of a SKILL.md ``---`` block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def _skill_dirs() -> dict[str, Traversable]:
    return {
        entry.name: entry
        for entry in sorted(_root().iterdir(), key=lambda e: e.name)
        if (entry / "SKILL.md").is_file()
    }


def list_skills() -> list[dict[str, str]]:
    """Name and description of every bundled skill."""
    skills = []
    for name, directory in _skill_dirs().items():
        meta = _parse_frontmatter((directory / "SKILL.md").read_text(encoding="utf-8"))
        skills.append({"name": name, "description": meta.get("description", "")})
    return skills


def _find(name: str) -> Traversable:
    dirs = _skill_dirs()
    if name not in dirs:
        raise ValueError(f"unknown skill {name!r}; available: {', '.join(dirs)}")
    return dirs[name]


def get_skill(name: str, full: bool = False) -> str:
    """SKILL.md text for ``name``; ``full`` appends every ``docs/*.md``."""
    directory = _find(name)
    parts = [(directory / "SKILL.md").read_text(encoding="utf-8").rstrip()]
    docs = directory / "docs"
    if full and docs.is_dir():
        for doc in sorted(docs.iterdir(), key=lambda e: e.name):
            if doc.name.endswith(".md"):
                body = doc.read_text(encoding="utf-8").rstrip()
                parts.append(f"--- docs/{doc.name} ---\n\n{body}")
    return "\n\n".join(parts)


def skill_path(name: str) -> str:
    """Filesystem path of the skill's directory."""
    return str(_find(name))


def default_root(project: bool = False) -> Path:
    """Where Claude Code looks for skills: ``~/.claude/skills`` or ``./.claude/skills``."""
    base = Path.cwd() if project else Path.home()
    return base / ".claude" / "skills"


def install_skills(root: Path, force: bool = False) -> list[dict[str, str]]:
    """Write the full ``llm-browser`` skill to ``root/llm-browser/SKILL.md``.

    The file is ``get_skill(..., full=True)``: SKILL.md with every docs/*.md
    inlined, so the skill is one self-contained file with no docs/ directory.

    An existing destination is left alone unless ``force``, which replaces
    it. A symlinked destination is unlinked, never followed, so forcing over
    a repo checkout's ``.claude/skills/llm-browser`` symlink can't touch the
    bundled source it points at.
    """
    text = get_skill(INSTALLED_SKILL, full=True)
    dest = root / INSTALLED_SKILL
    if dest.is_symlink() or dest.exists():
        if not force:
            return [{"name": INSTALLED_SKILL, "path": str(dest), "status": "skipped"}]
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(text + "\n", encoding="utf-8")
    return [{"name": INSTALLED_SKILL, "path": str(dest), "status": "installed"}]
