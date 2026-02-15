"""User and project settings storage for deepagents-cli."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            # Arrays and scalars fully override
            result[key] = value
    return result


@dataclass
class SettingsStore:
    """Loads and writes DeepAgents settings with project overrides."""

    project_root: Path | None

    @property
    def global_path(self) -> Path:
        return Path.home() / ".deepagents" / "settings.json"

    @property
    def project_path(self) -> Path | None:
        if not self.project_root:
            return None
        return self.project_root / ".deepagents" / "settings.json"

    def load(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for path in [self.global_path, self.project_path]:
            if not path or not path.exists():
                continue
            try:
                content = json.loads(path.read_text())
            except Exception:
                continue
            if isinstance(content, dict):
                data = _deep_merge(data, content)
        return data

    def _parse_model_ref(self, value: str) -> dict[str, str] | None:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        if "/" in text:
            provider, model_id = text.split("/", 1)
        elif ":" in text:
            provider, model_id = text.split(":", 1)
        else:
            return None
        provider = provider.strip()
        model_id = model_id.strip()
        if not provider or not model_id:
            return None
        return {"provider": provider, "id": model_id}

    def _load_path(self, path: Path | None) -> dict[str, Any]:
        if not path or not path.exists():
            return {}
        try:
            content = json.loads(path.read_text())
        except Exception:
            return {}
        if isinstance(content, dict):
            return content
        return {}

    def save(self, data: dict[str, Any], *, scope: str = "global") -> None:
        if scope == "project" and self.project_path is not None:
            path = self.project_path
        else:
            path = self.global_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

    def get_active_model(self) -> Any:
        settings = self.load()
        model_section = settings.get("model")
        if isinstance(model_section, dict):
            return model_section.get("active")
        default_provider = settings.get("defaultProvider")
        default_model = settings.get("defaultModel")
        if isinstance(default_model, str):
            parsed = self._parse_model_ref(default_model)
            if parsed:
                return parsed
            if isinstance(default_provider, str) and default_provider.strip():
                return {"provider": default_provider.strip(), "id": default_model.strip()}
        return None

    def set_active_model(self, active: Any, *, scope: str = "global") -> None:
        if scope == "project":
            settings = self._load_path(self.project_path)
        else:
            settings = self._load_path(self.global_path)
        model_section: dict[str, Any] = {}
        if isinstance(settings.get("model"), dict):
            model_section = dict(settings.get("model") or {})
        model_section["active"] = active
        settings["model"] = model_section
        self.save(settings, scope=scope)

    def get_default_reasoning(self) -> str | None:
        settings = self.load()
        model_section = settings.get("model")
        if isinstance(model_section, dict):
            value = model_section.get("reasoning")
            if isinstance(value, str):
                return value.strip().lower() or None
        default_thinking = settings.get("defaultThinkingLevel")
        if isinstance(default_thinking, str):
            return default_thinking.strip().lower() or None
        return None

    def get_default_service_tier(self) -> str | None:
        settings = self.load()
        model_section = settings.get("model")
        if isinstance(model_section, dict):
            value = model_section.get("service_tier")
            if isinstance(value, str):
                return value.strip() or None
        return None

    def get_provider_overrides(self) -> dict[str, Any]:
        settings = self.load()
        providers = settings.get("providers")
        if isinstance(providers, dict):
            return providers
        return {}

    def get_enabled_models(self) -> list[str]:
        settings = self.load()
        enabled: list[Any] = []
        model_section = settings.get("model")
        if isinstance(model_section, dict) and isinstance(model_section.get("enabled"), list):
            enabled = model_section.get("enabled") or []
        elif isinstance(settings.get("enabledModels"), list):
            enabled = settings.get("enabledModels") or []
        result: list[str] = []
        for entry in enabled:
            if isinstance(entry, str):
                parsed = self._parse_model_ref(entry)
                if parsed:
                    result.append(f"{parsed['provider']}:{parsed['id']}")
                else:
                    text = entry.strip()
                    if text:
                        result.append(text)
            elif isinstance(entry, dict):
                provider = entry.get("provider")
                model_id = entry.get("id") or entry.get("model")
                if provider and model_id:
                    result.append(f"{str(provider).strip()}:{str(model_id).strip()}")
        return [item for item in result if item.strip()]
