"""Bundled Claude Code skill commands."""

from __future__ import annotations

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
