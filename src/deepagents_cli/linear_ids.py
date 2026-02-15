"""Shared helpers for Linear issue identifier validation."""

from __future__ import annotations

import re

LINEAR_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]+-\d+$")


def is_linear_identifier(value: str) -> bool:
    """Return True when *value* matches TEAM-123 style Linear identifiers."""
    return bool(LINEAR_IDENTIFIER_RE.match(value.strip()))
