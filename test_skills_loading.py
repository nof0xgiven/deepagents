"""Tests for CLI skill loading precedence across default, user, and project sources."""

from __future__ import annotations

import os
from pathlib import Path

from deepagents_cli.skills.load import list_skills


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: {description}
---

# {name}
""",
        encoding="utf-8",
    )


def test_list_skills_source_precedence(tmp_path: Path) -> None:
    default_dir = tmp_path / "default"
    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"

    _write_skill(default_dir, "shared", "default shared")
    _write_skill(default_dir, "default-only", "default only")
    _write_skill(user_dir, "shared", "user shared")
    _write_skill(user_dir, "user-only", "user only")
    _write_skill(project_dir, "shared", "project shared")
    _write_skill(project_dir, "project-only", "project only")

    skills = list_skills(
        default_skills_dir=default_dir,
        user_skills_dir=user_dir,
        project_skills_dir=project_dir,
    )
    by_name = {skill["name"]: skill for skill in skills}

    assert by_name["shared"]["source"] == "project"
    assert Path(by_name["shared"]["path"]).parent == project_dir / "shared"
    assert by_name["default-only"]["source"] == "default"
    assert by_name["user-only"]["source"] == "user"
    assert by_name["project-only"]["source"] == "project"


def test_list_skills_missing_default_dir(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"
    _write_skill(user_dir, "shared", "user shared")
    _write_skill(project_dir, "shared", "project shared")

    skills = list_skills(
        default_skills_dir=tmp_path / "missing-default",
        user_skills_dir=user_dir,
        project_skills_dir=project_dir,
    )
    by_name = {skill["name"]: skill for skill in skills}

    assert by_name["shared"]["source"] == "project"
    assert Path(by_name["shared"]["path"]).parent == project_dir / "shared"


def test_list_skills_skips_unreadable_source(tmp_path: Path) -> None:
    default_dir = tmp_path / "default"
    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"

    broken_skill_dir = default_dir / "broken-skill"
    broken_skill_dir.mkdir(parents=True, exist_ok=True)
    # Create a self-referential symlink to trigger a read error.
    os.symlink("SKILL.md", broken_skill_dir / "SKILL.md")

    _write_skill(user_dir, "shared", "user shared")
    _write_skill(project_dir, "shared", "project shared")

    skills = list_skills(
        default_skills_dir=default_dir,
        user_skills_dir=user_dir,
        project_skills_dir=project_dir,
    )
    by_name = {skill["name"]: skill for skill in skills}

    assert by_name["shared"]["source"] == "project"
    assert Path(by_name["shared"]["path"]).parent == project_dir / "shared"
