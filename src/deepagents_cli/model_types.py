"""Shared model and provider types for deepagents-cli."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuthRef:
    """Reference to credentials for a provider."""

    source: str  # "auth_json" | "env" | "inline"
    key: str


@dataclass(frozen=True)
class ProviderConfig:
    """Provider-level configuration."""

    name: str
    api: str
    base_url: str | None
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, Any] = field(default_factory=dict)
    auth: AuthRef | None = None
    source: Path | None = None


@dataclass(frozen=True)
class ModelEntry:
    """Model definition resolved from catalogs/settings."""

    id: str
    name: str
    alias: str
    provider: str
    api: str
    base_url: str | None
    reasoning_effort: str | None
    reasoning_enabled: bool | None
    service_tier: str | None
    inputs: list[str] | None
    max_tokens: int | None
    context_window: int | None
    compat: dict[str, Any]
    source: Path

    @property
    def display_name(self) -> str:
        return self.name or self.alias or self.id

    def identity(self) -> str:
        return f"{self.provider}:{self.id}"
