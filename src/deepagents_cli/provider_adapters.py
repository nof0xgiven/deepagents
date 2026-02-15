"""Provider adapters for deepagents-cli."""

from __future__ import annotations

from typing import Any
import inspect

from langchain_core.language_models import BaseChatModel

from deepagents_cli.auth_store import AuthCredentials
from deepagents_cli.model_types import ModelEntry, ProviderConfig
from deepagents_cli.openai_compat import patch_responses_usage


class ProviderError(RuntimeError):
    pass


def _merge_headers(provider: ProviderConfig, entry: ModelEntry) -> dict[str, str]:
    headers = dict(provider.headers)
    compat_headers = entry.compat.get("headers") if isinstance(entry.compat, dict) else None
    if isinstance(compat_headers, dict):
        headers.update({str(k): str(v) for k, v in compat_headers.items()})
    return headers


def _filter_kwargs(callable_obj: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return kwargs
    for param in sig.parameters.values():
        if param.kind == param.VAR_KEYWORD:
            return kwargs
    return {key: value for key, value in kwargs.items() if key in sig.parameters}


def _drop_none(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def create_chat_model(
    entry: ModelEntry,
    provider: ProviderConfig,
    auth: AuthCredentials,
    *,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
) -> BaseChatModel:
    api = entry.api or provider.api
    base_url = entry.base_url or provider.base_url
    headers = _merge_headers(provider, entry)

    if api == "openai-responses":
        from langchain_openai import ChatOpenAI

        patch_responses_usage()
        kwargs = {
            "model": entry.id,
            "api_key": auth.token,
            "base_url": base_url,
            "default_headers": headers or None,
            "use_responses_api": True,
            "reasoning_effort": reasoning_effort,
            "service_tier": service_tier,
        }
        return ChatOpenAI(**_filter_kwargs(ChatOpenAI, _drop_none(kwargs)))

    if api == "openai-completions":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": entry.id,
            "api_key": auth.token,
            "base_url": base_url,
            "default_headers": headers or None,
            "use_responses_api": False,
        }
        return ChatOpenAI(**_filter_kwargs(ChatOpenAI, _drop_none(kwargs)))

    if api == "anthropic-messages":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ProviderError("langchain-anthropic is required for Anthropic models") from exc
        is_oauth = auth.kind == "oauth"
        merged_headers = dict(headers) if headers else {}
        if is_oauth:
            merged_headers["anthropic-beta"] = "oauth-2025-04-20"
        kwargs: dict[str, Any] = {
            "model_name": entry.id,
            "api_key": "placeholder" if is_oauth else auth.token,
        }
        if merged_headers:
            kwargs["default_headers"] = merged_headers
        if base_url:
            kwargs["base_url"] = base_url
        max_tokens = entry.max_tokens
        if max_tokens:
            kwargs["max_tokens_to_sample"] = max_tokens
        model = ChatAnthropic(**_filter_kwargs(ChatAnthropic, _drop_none(kwargs)))
        if is_oauth:
            # ChatAnthropic doesn't expose auth_token, so we patch the
            # underlying Anthropic clients to use Bearer auth instead of
            # x-api-key after construction.
            model._client.api_key = None  # type: ignore[assignment]
            model._client.auth_token = auth.token
            model._async_client.api_key = None  # type: ignore[assignment]
            model._async_client.auth_token = auth.token
        return model

    if api == "google-generative-ai":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ProviderError("langchain-google-genai is required for Google models") from exc
        kwargs: dict[str, Any] = {
            "model": entry.id,
        }
        if auth.kind == "oauth":
            try:
                from google.oauth2.credentials import Credentials
            except ImportError as exc:
                raise ProviderError("google-auth is required for Google OAuth") from exc
            creds = Credentials(
                token=auth.raw.access,
                refresh_token=auth.raw.refresh,
                token_uri=auth.raw.token_url,
                client_id=auth.raw.client_id,
                client_secret=auth.raw.client_secret,
                scopes=auth.raw.scopes,
            )
            kwargs["credentials"] = creds
        else:
            kwargs["google_api_key"] = auth.token
        return ChatGoogleGenerativeAI(**_filter_kwargs(ChatGoogleGenerativeAI, _drop_none(kwargs)))

    raise ProviderError(f"Unsupported provider api type: {api}")
