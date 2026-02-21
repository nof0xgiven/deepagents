"""Skill loader for CLI commands.

This module provides filesystem-based skill loading for CLI operations (list, create, info).
It wraps the prebuilt middleware functionality from deepagents.middleware.skills and adapts
it for direct filesystem access needed by CLI commands.

For middleware usage within agents, use deepagents.middleware.skills.SkillsMiddleware directly.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import SkillMetadata, _parse_skill_metadata

logger = logging.getLogger(__name__)


class ExtendedSkillMetadata(SkillMetadata):
    """Extended skill metadata for CLI display, adds source tracking."""

    source: str


# Re-export for CLI commands
__all__ = ["SkillMetadata", "list_skills"]


def _load_skills_from_source(
    *, source_dir: Path | None, source_name: str
) -> list[ExtendedSkillMetadata]:
    if not source_dir or not source_dir.exists():
        return []

    try:
        backend = FilesystemBackend(root_dir=str(source_dir))
        items = backend.ls_info(".")
    except Exception as exc:
        logger.warning(
            "Skipping unreadable %s skills source %s: %s",
            source_name,
            source_dir,
            exc,
        )
        return []

    loaded: list[ExtendedSkillMetadata] = []
    for item in items:
        if not item.get("is_dir"):
            continue

        skill_dir_path = item.get("path")
        if not isinstance(skill_dir_path, str):
            continue

        skill_dir = PurePosixPath(skill_dir_path)
        skill_md_path = str(skill_dir / "SKILL.md")
        try:
            response = backend.download_files([skill_md_path])[0]
        except Exception as exc:
            logger.debug("Skipping unreadable skill file %s: %s", skill_md_path, exc)
            continue

        if response.error or response.content is None:
            continue

        try:
            content = response.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.debug("Skipping undecodable skill file %s: %s", skill_md_path, exc)
            continue

        metadata = _parse_skill_metadata(
            content=content,
            skill_path=skill_md_path,
            directory_name=skill_dir.name,
        )
        if metadata:
            loaded.append({**metadata, "source": source_name})

    return loaded


def list_skills(
    *,
    default_skills_dir: Path | None = None,
    user_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
) -> list[ExtendedSkillMetadata]:
    """List skills from default, user, and/or project directories.

    This is a CLI-specific wrapper around the prebuilt middleware's skill loading
    functionality. It uses FilesystemBackend to load skills from local directories.

    Sources are loaded in precedence order:
    default -> user -> project.
    Later sources override earlier ones when names conflict.

    Args:
        default_skills_dir: Path to the shared default skills directory.
        user_skills_dir: Path to the user-level skills directory.
        project_skills_dir: Path to the project-level skills directory.

    Returns:
        Merged list of skill metadata from all provided sources.
    """
    all_skills: dict[str, ExtendedSkillMetadata] = {}

    # Load default skills first (foundation)
    for skill in _load_skills_from_source(source_dir=default_skills_dir, source_name="default"):
        all_skills[skill["name"]] = skill

    # Load user skills second (override default)
    for skill in _load_skills_from_source(source_dir=user_skills_dir, source_name="user"):
        all_skills[skill["name"]] = skill

    # Load project skills third (highest priority)
    for skill in _load_skills_from_source(source_dir=project_skills_dir, source_name="project"):
        all_skills[skill["name"]] = skill

    return list(all_skills.values())
