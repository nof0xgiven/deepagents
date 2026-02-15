"""Model registry utilities for deepagents-cli."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepagents_cli.model_types import AuthRef, ModelEntry, ProviderConfig
from deepagents_cli.settings_store import SettingsStore

MODEL_STATE_PATH = Path.home() / ".deepagents" / "model_state.json"
MODELS_PATH = Path.home() / ".deepagents" / "models.json"


@dataclass(frozen=True)
class ModelCatalog:
    models: list[ModelEntry]
    providers: dict[str, ProviderConfig]


def _looks_like_env(value: str) -> bool:
    return value.isupper() and "_" in value


def _parse_auth_ref(data: dict[str, Any]) -> AuthRef | None:
    auth = data.get("auth")
    if isinstance(auth, dict):
        source = auth.get("source") or auth.get("type")
        key = auth.get("key") or auth.get("env") or auth.get("value")
        if source and key:
            source = str(source)
            if source == "env":
                return AuthRef(source="env", key=str(key))
            if source == "inline":
                return AuthRef(source="inline", key=str(key))
            return AuthRef(source="auth_json", key=str(key))
    if isinstance(auth, str) and auth.strip():
        value = auth.strip()
        if _looks_like_env(value):
            return AuthRef(source="env", key=value)
        return AuthRef(source="auth_json", key=value)

    api_key = data.get("api_key") or data.get("apiKey")
    if isinstance(api_key, str) and api_key.strip():
        value = api_key.strip()
        if _looks_like_env(value):
            return AuthRef(source="env", key=value)
        return AuthRef(source="inline", key=value)

    auth_env = data.get("auth_env") or data.get("authEnv")
    if isinstance(auth_env, str) and auth_env.strip():
        return AuthRef(source="env", key=auth_env.strip())
    return None


def _normalize_reasoning(value: Any) -> tuple[str | None, bool | None]:
    if isinstance(value, bool):
        return (None, value)
    if isinstance(value, str):
        val = value.strip().lower()
        if not val:
            return (None, None)
        if val in {"false", "off", "none", "no"}:
            return (None, False)
        return (val, True)
    return (None, None)


def _detect_provider(model_name: str) -> str | None:
    model_lower = model_name.lower()
    if model_lower.startswith(("gpt-", "o1-", "o3-")):
        return "openai"
    if model_lower.startswith("claude-"):
        return "anthropic"
    if model_lower.startswith("gemini-"):
        return "google"
    return None


def _parse_provider(name: str, data: dict[str, Any], source: Path) -> ProviderConfig:
    api = str(data.get("api") or "openai-responses").strip()
    base_url = data.get("base_url") or data.get("baseUrl")
    if isinstance(base_url, str):
        base_url = base_url.strip() or None
    else:
        base_url = None
    headers = data.get("headers")
    if not isinstance(headers, dict):
        headers = {}
    compat = data.get("compat")
    if not isinstance(compat, dict):
        compat = {}
    auth_ref = _parse_auth_ref(data)
    return ProviderConfig(
        name=name,
        api=api,
        base_url=base_url,
        headers={str(k): str(v) for k, v in headers.items()},
        compat=compat,
        auth=auth_ref,
        source=source,
    )


def _merge_provider(base: ProviderConfig, override: dict[str, Any], source: Path) -> ProviderConfig:
    merged = {
        "api": override.get("api") or base.api,
        "base_url": override.get("base_url") or override.get("baseUrl") or base.base_url,
        "headers": {**base.headers},
        "compat": {**base.compat},
        "auth": base.auth,
    }
    if isinstance(override.get("headers"), dict):
        merged["headers"].update(override.get("headers") or {})
    if isinstance(override.get("compat"), dict):
        merged["compat"].update(override.get("compat") or {})
    override_auth = _parse_auth_ref(override)
    if override_auth is not None:
        merged["auth"] = override_auth
    return ProviderConfig(
        name=base.name,
        api=str(merged["api"]).strip(),
        base_url=str(merged["base_url"]).strip() if merged["base_url"] else None,
        headers=merged["headers"],
        compat=merged["compat"],
        auth=merged["auth"],
        source=source,
    )


def _parse_model(
    provider_name: str,
    provider: ProviderConfig,
    model: dict[str, Any],
    source: Path,
) -> ModelEntry | None:
    model_id = str(model.get("id") or "").strip()
    if not model_id:
        return None
    name = str(model.get("name") or model_id).strip()
    alias = str(model.get("alias") or model.get("name") or model_id).strip()
    api = str(model.get("api") or provider.api).strip()
    base_url = model.get("base_url") or model.get("baseUrl") or provider.base_url
    if isinstance(base_url, str):
        base_url = base_url.strip() or None
    else:
        base_url = None
    reasoning_effort, reasoning_enabled = _normalize_reasoning(
        model.get("reasoning") or model.get("reasoning_effort")
    )
    service_tier = model.get("service_tier") or model.get("serviceTier")
    if isinstance(service_tier, str):
        service_tier = service_tier.strip() or None
    else:
        service_tier = None
    inputs = model.get("input") or model.get("inputs")
    if isinstance(inputs, list):
        inputs = [str(item) for item in inputs if str(item).strip()]
    else:
        inputs = None
    max_tokens = model.get("max_tokens") or model.get("maxTokens")
    if isinstance(max_tokens, str) and max_tokens.isdigit():
        max_tokens = int(max_tokens)
    if not isinstance(max_tokens, int):
        max_tokens = None
    context_window = model.get("context_window") or model.get("contextWindow")
    if isinstance(context_window, str) and context_window.isdigit():
        context_window = int(context_window)
    if not isinstance(context_window, int):
        context_window = None
    compat = model.get("compat")
    if not isinstance(compat, dict):
        compat = {}
    if service_tier is None:
        compat_service = compat.get("serviceTier") or compat.get("service_tier")
        if isinstance(compat_service, str):
            service_tier = compat_service.strip() or None
    return ModelEntry(
        id=model_id,
        name=name,
        alias=alias or model_id,
        provider=provider_name,
        api=api,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
        reasoning_enabled=reasoning_enabled,
        service_tier=service_tier,
        inputs=inputs,
        max_tokens=max_tokens,
        context_window=context_window,
        compat=compat,
        source=source,
    )


def _load_models_from_file(path: Path) -> ModelCatalog:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ModelCatalog(models=[], providers={})

    providers: dict[str, ProviderConfig] = {}
    models: list[ModelEntry] = []

    providers_data = data.get("providers")
    if isinstance(providers_data, dict):
        for name, provider_data in providers_data.items():
            if not isinstance(provider_data, dict):
                continue
            provider = _parse_provider(str(name), provider_data, path)
            providers[provider.name] = provider
            provider_models = provider_data.get("models")
            if isinstance(provider_models, list):
                for model in provider_models:
                    if isinstance(model, dict):
                        entry = _parse_model(provider.name, provider, model, path)
                        if entry:
                            models.append(entry)

    global_models = data.get("models")
    if isinstance(global_models, list):
        for model in global_models:
            if not isinstance(model, dict):
                continue
            model_provider = model.get("provider")
            provider_name = str(model_provider).strip() if model_provider else ""
            if not provider_name:
                detected = _detect_provider(str(model.get("id") or ""))
                provider_name = detected or ""
            if not provider_name:
                continue
            provider = providers.get(provider_name)
            if not provider:
                provider = ProviderConfig(
                    name=provider_name,
                    api=str(model.get("api") or "openai-responses").strip(),
                    base_url=None,
                    source=path,
                )
                providers[provider_name] = provider
            entry = _parse_model(provider.name, provider, model, path)
            if entry:
                models.append(entry)

    return ModelCatalog(models=models, providers=providers)


def _load_settings_overrides(project_root: Path | None) -> dict[str, Any]:
    store = SettingsStore(project_root)
    return store.get_provider_overrides()


def _parse_model_ref(value: str) -> tuple[str, str] | None:
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
    return provider, model_id


def _builtin_provider_config(name: str) -> ProviderConfig | None:
    provider = name.strip()
    lowered = provider.lower()
    if lowered in {"openai", "openai-codex"}:
        return ProviderConfig(name=provider, api="openai-responses", base_url=None)
    if lowered == "anthropic":
        return ProviderConfig(name=provider, api="anthropic-messages", base_url=None)
    if lowered == "google":
        return ProviderConfig(name=provider, api="google-generative-ai", base_url=None)
    return None


def load_model_catalog(*, project_root: Path | None = None) -> ModelCatalog:
    """Load model entries from user config files.

    Searches ~/.deepagents/models.json and merges settings overrides.
    """
    catalog = ModelCatalog(models=[], providers={})
    if MODELS_PATH.exists():
        catalog = _load_models_from_file(MODELS_PATH)

    overrides = _load_settings_overrides(project_root)
    if overrides:
        for name, override in overrides.items():
            if not isinstance(override, dict):
                continue
            if name in catalog.providers:
                catalog.providers[name] = _merge_provider(
                    catalog.providers[name], override, catalog.providers[name].source or MODELS_PATH
                )
            else:
                catalog.providers[name] = _parse_provider(name, override, MODELS_PATH)

    settings_store = SettingsStore(project_root)
    enabled = settings_store.get_enabled_models()
    if enabled:
        allowed = [item for item in enabled if item and str(item).strip()]
        allowed_lower = {str(item).strip().lower() for item in allowed}

        existing_lower = {model_key(entry).lower(): entry for entry in catalog.models}
        for item in allowed:
            parsed = _parse_model_ref(str(item))
            if not parsed:
                continue
            provider_name, model_id = parsed
            key_lower = f"{provider_name.lower()}:{model_id.lower()}"
            if key_lower in existing_lower:
                continue
            provider = catalog.providers.get(provider_name) or _builtin_provider_config(provider_name)
            if not provider:
                continue
            entry = ModelEntry(
                id=model_id,
                name=model_id,
                alias=model_id,
                provider=provider.name,
                api=provider.api,
                base_url=provider.base_url,
                reasoning_effort=None,
                reasoning_enabled=None,
                service_tier=None,
                inputs=None,
                max_tokens=None,
                context_window=None,
                compat={},
                source=Path("settings"),
            )
            catalog.models.append(entry)
            existing_lower[key_lower] = entry
            if provider.name not in catalog.providers:
                catalog.providers[provider.name] = provider

        catalog = ModelCatalog(
            models=[entry for entry in catalog.models if model_key(entry).lower() in allowed_lower],
            providers=catalog.providers,
        )
    return catalog


def load_model_state() -> dict[str, list[str]]:
    if not MODEL_STATE_PATH.exists():
        return {"favorites": [], "recent": []}
    try:
        data = json.loads(MODEL_STATE_PATH.read_text())
    except Exception:
        return {"favorites": [], "recent": []}
    favorites = data.get("favorites")
    recent = data.get("recent")
    if not isinstance(favorites, list):
        favorites = []
    if not isinstance(recent, list):
        recent = []
    return {
        "favorites": [str(item) for item in favorites if str(item).strip()],
        "recent": [str(item) for item in recent if str(item).strip()],
    }


def save_model_state(state: dict[str, list[str]]) -> None:
    MODEL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "favorites": state.get("favorites", []),
        "recent": state.get("recent", []),
    }
    MODEL_STATE_PATH.write_text(json.dumps(payload, indent=2))


def model_key(entry: ModelEntry) -> str:
    return entry.identity()


def update_recent(state: dict[str, list[str]], key: str, limit: int = 10) -> None:
    recent = [item for item in state.get("recent", []) if item != key]
    recent.insert(0, key)
    state["recent"] = recent[:limit]


def toggle_favorite(state: dict[str, list[str]], key: str) -> bool:
    favorites = list(state.get("favorites", []))
    if key in favorites:
        favorites = [item for item in favorites if item != key]
        state["favorites"] = favorites
        return False
    favorites.insert(0, key)
    state["favorites"] = favorites
    return True


def _score_match(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    query_lower = query.lower()
    candidate_lower = candidate.lower()
    if query_lower == candidate_lower:
        return 3.0
    if query_lower in candidate_lower:
        return 2.0 + (len(query_lower) / max(len(candidate_lower), 1))
    overlap = sum(1 for ch in query_lower if ch in candidate_lower)
    return overlap / max(len(candidate_lower), 1)


def search_models(query: str, entries: list[ModelEntry], limit: int = 10) -> list[ModelEntry]:
    if not query:
        return entries[:limit]
    scored: list[tuple[float, ModelEntry]] = []
    for entry in entries:
        score = max(
            _score_match(query, entry.alias),
            _score_match(query, entry.id),
            _score_match(query, entry.name),
            _score_match(query, entry.provider),
        )
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _score, entry in scored[:limit]]


def resolve_model_query(query: str, entries: list[ModelEntry]) -> ModelEntry | None:
    query_lower = query.strip().lower()
    if not query_lower:
        return None
    for entry in entries:
        if entry.alias.lower() == query_lower:
            return entry
        if entry.id.lower() == query_lower:
            return entry
        if entry.name.lower() == query_lower:
            return entry
        if f"{entry.provider}:{entry.id}".lower() == query_lower:
            return entry
    if ":" in query_lower:
        provider, model_id = query_lower.split(":", 1)
        for entry in entries:
            if entry.provider.lower() == provider and entry.id.lower() == model_id:
                return entry
    return None
