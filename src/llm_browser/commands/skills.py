"""Bundled Claude Code skill commands."""

from __future__ import annotations

from pathlib import Path

import typer

from llm_browser.browser import skills
from llm_browser.commands import _print


def register(skills_app: typer.Typer) -> None:
    @skills_app.command(name="list")
    def list_cmd(
        json: bool = typer.Option(False, "--json", help="Output as JSON."),
    ) -> None:
        """List the bundled skills with their descriptions."""
        found = skills.list_skills()
        if json:
            _print(found)
        else:
            for skill in found:
                print(f"{skill['name']}: {skill['description']}")

    @skills_app.command(name="get")
    def get_cmd(
        name: str = typer.Argument(..., help="Skill name (see `skills list`)."),
        full: bool = typer.Option(
            False, "--full", help="Also print the skill's docs/*.md files."
        ),
        path: bool = typer.Option(
            False, "--path", help="Print the skill's directory instead of its text."
        ),
    ) -> None:
        """Print a skill's SKILL.md."""
        print(skills.skill_path(name) if path else skills.get_skill(name, full=full))

    @skills_app.command(name="install")
    def install_cmd(
        project: bool = typer.Option(
            False,
            "--project",
            help="Install into ./.claude/skills, not ~/.claude/skills.",
        ),
        dir: Path = typer.Option(
            None, "--dir", help="Install into this skills directory instead."
        ),
        force: bool = typer.Option(
            False, "--force", help="Replace skills that are already installed."
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON."),
    ) -> None:
        """Install the full llm-browser skill (docs inlined) for Claude Code (~/.claude/skills)."""
        if project and dir is not None:
            raise typer.BadParameter("--project and --dir are mutually exclusive.")
        root = dir if dir is not None else skills.default_root(project)
        results = skills.install_skills(root, force=force)
        if json:
            _print(results)
            return
        for r in results:
            if r["status"] == "installed":
                print(f"installed {r['name']} -> {r['path']}")
            else:
                print(f"skipped {r['name']} (exists; use --force): {r['path']}")
