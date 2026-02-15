"""Model selection/catalog state management."""

from __future__ import annotations

from pathlib import Path

from deepagents_cli.config import settings
from deepagents_cli.model_registry import (
    ModelEntry,
    load_model_catalog,
    load_model_state,
    resolve_model_query,
    save_model_state,
    update_recent,
)
from deepagents_cli.settings_store import SettingsStore


class ModelController:
    """Owns model selector state and model-catalog helpers."""

    def __init__(self, *, project_root: Path | None) -> None:
        self._project_root = project_root
        self._model_candidates: list[ModelEntry] = []
        self._model_selector_open = False
        self._last_model_entry: ModelEntry | None = None

    @property
    def model_candidates(self) -> list[ModelEntry]:
        return self._model_candidates

    def set_model_candidates(self, entries: list[ModelEntry]) -> None:
        self._model_candidates = entries

    @property
    def model_selector_open(self) -> bool:
        return self._model_selector_open

    def set_model_selector_open(self, *, is_open: bool) -> None:
        self._model_selector_open = is_open

    @property
    def last_model_entry(self) -> ModelEntry | None:
        return self._last_model_entry

    @staticmethod
    def strip_model_prefix(model_name: str) -> str:
        """Normalize model names by stripping known provider prefixes."""
        value = model_name.strip()
        for prefix in ("openai:", "anthropic:", "google:"):
            if value.lower().startswith(prefix):
                return value[len(prefix) :].strip()
        return value

    @staticmethod
    def truncate_model_name(name: str) -> str:
        """Trim verbose provider prefixes for status-bar display."""
        value = name.strip()
        for prefix in ("claude-", "models/"):
            if value.startswith(prefix):
                value = value[len(prefix) :]
                break
        return value

    @staticmethod
    def format_model_entry(entry: ModelEntry, index: int | None = None) -> str:
        """Render model options consistently for `/model <query>` results."""
        label = f"{entry.display_name} — {entry.provider}/{entry.id}"
        suffix_parts: list[str] = []
        if entry.reasoning_effort:
            suffix_parts.append(f"reasoning={entry.reasoning_effort}")
        if entry.reasoning_enabled is False:
            suffix_parts.append("reasoning=off")
        if entry.service_tier:
            suffix_parts.append(f"tier={entry.service_tier}")
        if suffix_parts:
            label = f"{label} ({', '.join(suffix_parts)})"
        if index is not None:
            return f"{index}. {label}"
        return label

    def build_model_catalog(self) -> list[ModelEntry]:
        """Build model entries from catalogs and current active selection."""
        catalog = load_model_catalog(project_root=self._project_root)
        entries = list(catalog.models)
        active = SettingsStore(self._project_root).get_active_model()
        if isinstance(active, dict):
            provider_name = str(active.get("provider") or "").strip()
            if provider_name:
                provider = catalog.providers.get(provider_name)
                if provider:
                    model_id = str(active.get("id") or "").strip()
                    if model_id and not any(
                        entry.provider == provider_name and entry.id == model_id for entry in entries
                    ):
                        entry = ModelEntry(
                            id=model_id,
                            name=str(active.get("name") or model_id).strip(),
                            alias=str(active.get("alias") or active.get("name") or model_id).strip(),
                            provider=provider_name,
                            api=str(active.get("api") or provider.api).strip(),
                            base_url=active.get("base_url")
                            or active.get("baseUrl")
                            or provider.base_url,
                            reasoning_effort=None,
                            reasoning_enabled=None,
                            service_tier=None,
                            inputs=None,
                            max_tokens=None,
                            context_window=None,
                            compat={},
                            source=Path("settings"),
                        )
                        entries.append(entry)
        return entries

    def persist_active_selection(self, entry: ModelEntry) -> None:
        """Persist active-model metadata and update recents."""
        state = load_model_state()
        update_recent(state, entry.identity())
        save_model_state(state)
        SettingsStore(self._project_root).set_active_model(
            {
                "provider": entry.provider,
                "id": entry.id,
                "alias": entry.alias,
                "api": entry.api,
                "base_url": entry.base_url,
            }
        )
        self._last_model_entry = entry

    def format_debug_model(self) -> list[str]:
        """Render debug output for current model resolution."""
        store = SettingsStore(self._project_root)
        active = store.get_active_model()
        enabled = store.get_enabled_models()
        catalog = load_model_catalog(project_root=self._project_root)
        resolved: ModelEntry | None = None
        if isinstance(active, dict):
            provider = str(active.get("provider") or "").strip()
            model_id = str(active.get("id") or "").strip()
            if provider and model_id:
                for entry in catalog.models:
                    if entry.provider == provider and entry.id == model_id:
                        resolved = entry
                        break
        elif isinstance(active, str):
            resolved = resolve_model_query(active, catalog.models)

        if resolved is None and self._last_model_entry is not None:
            resolved = self._last_model_entry

        lines = [
            "Debug: model selection",
            f"settings.model_provider: {settings.model_provider or 'none'}",
            f"settings.model_name: {settings.model_name or 'none'}",
            f"settings.model.active: {active if active else 'none'}",
            f"catalog.models: {len(catalog.models)}",
        ]
        if enabled:
            lines.append(f"enabled allow-list: {len(enabled)} entries")
        else:
            lines.append("enabled allow-list: none")

        if resolved:
            lines.extend(
                [
                    f"resolved.provider: {resolved.provider}",
                    f"resolved.id: {resolved.id}",
                    f"resolved.api: {resolved.api}",
                    f"resolved.base_url: {resolved.base_url or 'default'}",
                    f"resolved.reasoning_effort: {resolved.reasoning_effort or 'none'}",
                    f"resolved.reasoning_enabled: {resolved.reasoning_enabled}",
                    f"resolved.service_tier: {resolved.service_tier or 'none'}",
                ]
            )
        else:
            lines.append("resolved: none")
        return lines
