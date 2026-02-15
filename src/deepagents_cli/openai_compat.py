"""Compatibility patches for OpenAI-compatible responses."""

from __future__ import annotations

from typing import Any, Callable


def patch_responses_usage() -> None:
    """Ensure missing usage values don't crash responses metadata parsing."""
    try:
        from langchain_openai.chat_models import base as lc_base
    except Exception:
        return

    if getattr(lc_base, "_DEEPAGENTS_PATCHED", False):
        return

    original: Callable[[dict[str, Any], str | None], Any] = lc_base._create_usage_metadata_responses

    def _safe_usage(oai_token_usage: dict[str, Any] | None, service_tier: str | None) -> Any:
        if oai_token_usage is None:
            usage: dict[str, Any] = {}
        else:
            usage = dict(oai_token_usage)
        if usage.get("input_tokens") is None:
            usage["input_tokens"] = 0
        if usage.get("output_tokens") is None:
            usage["output_tokens"] = 0
        if usage.get("total_tokens") is None:
            usage.pop("total_tokens", None)
        return original(usage, service_tier)

    lc_base._create_usage_metadata_responses = _safe_usage
    lc_base._DEEPAGENTS_PATCHED = True
