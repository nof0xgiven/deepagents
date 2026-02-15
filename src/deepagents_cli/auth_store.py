"""Authentication store for provider credentials."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from deepagents_cli.model_types import AuthRef

AUTH_PATH = Path.home() / ".deepagents" / "auth.json"

_KNOWN_TOKEN_URLS: dict[str, str] = {
    "anthropic": "https://console.anthropic.com/v1/oauth/token",
    "google": "https://oauth2.googleapis.com/token",
    "google-gemini-cli": "https://oauth2.googleapis.com/token",
}

_KNOWN_CLIENT_IDS: dict[str, str] = {
    "anthropic": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
}

# Providers whose token endpoints require JSON body instead of form-encoded.
_JSON_TOKEN_PROVIDERS: set[str] = {"anthropic"}


class AuthError(RuntimeError):
    pass


@dataclass
class AuthEntry:
    kind: str  # "api_key" | "oauth"
    key: str | None = None
    access: str | None = None
    refresh: str | None = None
    expires: int | None = None
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    extra: dict[str, Any] | None = None


@dataclass
class AuthCredentials:
    kind: str
    token: str
    raw: AuthEntry


class AuthStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or AUTH_PATH
        self._entries: dict[str, AuthEntry] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            self._entries[key] = self._parse_entry(value)

    def _parse_entry(self, value: dict[str, Any]) -> AuthEntry:
        kind = str(value.get("type") or value.get("kind") or "api_key").strip().lower()
        key = value.get("key") or value.get("apiKey") or value.get("api_key")
        access = value.get("access") or value.get("access_token")
        refresh = value.get("refresh") or value.get("refresh_token")
        expires = value.get("expires") or value.get("expires_at") or value.get("expiresAt")
        token_url = value.get("token_url") or value.get("tokenUrl")
        client_id = value.get("client_id") or value.get("clientId")
        client_secret = value.get("client_secret") or value.get("clientSecret")
        scopes = value.get("scopes")
        extra = value.get("extra")
        if isinstance(expires, str) and expires.isdigit():
            expires = int(expires)
        if isinstance(scopes, str):
            scopes = [item.strip() for item in scopes.split() if item.strip()]
        if not isinstance(scopes, list):
            scopes = None
        if not isinstance(extra, dict):
            extra = None
        if isinstance(expires, int) and expires < 10**12:
            expires = expires * 1000
        return AuthEntry(
            kind=kind,
            key=str(key) if key else None,
            access=str(access) if access else None,
            refresh=str(refresh) if refresh else None,
            expires=int(expires) if isinstance(expires, int) else None,
            token_url=str(token_url) if token_url else None,
            client_id=str(client_id) if client_id else None,
            client_secret=str(client_secret) if client_secret else None,
            scopes=scopes,
            extra=extra,
        )

    def get_entry(self, key: str) -> AuthEntry | None:
        self.load()
        return self._entries.get(key)

    def resolve(self, provider_name: str, auth_ref: AuthRef | None) -> AuthCredentials | None:
        self.load()
        if auth_ref is None:
            entry = self._entries.get(provider_name)
            if entry is None:
                return self._resolve_env(provider_name)
            return self._materialize(entry, provider_name)
        if auth_ref.source == "env":
            token = os.environ.get(auth_ref.key)
            if not token:
                return None
            return AuthCredentials(kind="api_key", token=token, raw=AuthEntry(kind="api_key", key=token))
        if auth_ref.source == "inline":
            return AuthCredentials(kind="api_key", token=auth_ref.key, raw=AuthEntry(kind="api_key", key=auth_ref.key))
        if auth_ref.source == "auth_json":
            entry = self._entries.get(auth_ref.key)
            if entry is None:
                return None
            return self._materialize(entry, auth_ref.key)
        return None

    def _resolve_env(self, provider_name: str) -> AuthCredentials | None:
        env_key = None
        if provider_name.lower() == "openai":
            env_key = "OPENAI_API_KEY"
        elif provider_name.lower() == "anthropic":
            env_key = "ANTHROPIC_API_KEY"
        elif provider_name.lower() == "google":
            env_key = "GOOGLE_API_KEY"
        if env_key:
            token = os.environ.get(env_key)
            if token:
                return AuthCredentials(kind="api_key", token=token, raw=AuthEntry(kind="api_key", key=token))
        return None

    def _materialize(self, entry: AuthEntry, entry_key: str) -> AuthCredentials:
        if entry.kind == "oauth":
            token = self._get_oauth_token(entry, entry_key)
            return AuthCredentials(kind="oauth", token=token, raw=entry)
        if entry.key:
            return AuthCredentials(kind="api_key", token=entry.key, raw=entry)
        raise AuthError("Missing API key for provider")

    def _get_oauth_token(self, entry: AuthEntry, entry_key: str) -> str:
        access = entry.access
        if not access:
            raise AuthError("OAuth entry missing access token")
        if entry.expires and entry.expires <= int(time.time() * 1000):
            refreshed = self._refresh_token(entry, entry_key)
            return refreshed
        return access

    def _refresh_token(self, entry: AuthEntry, entry_key: str) -> str:
        if not entry.refresh:
            raise AuthError("OAuth access token expired and no refresh token is available")
        provider_lower = entry_key.lower()
        token_url = entry.token_url or _KNOWN_TOKEN_URLS.get(provider_lower)
        if not token_url:
            raise AuthError("OAuth access token expired; set token_url to enable refresh")
        client_id = entry.client_id or _KNOWN_CLIENT_IDS.get(provider_lower)
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": entry.refresh,
        }
        if client_id:
            payload["client_id"] = client_id
        if entry.client_secret:
            payload["client_secret"] = entry.client_secret
        if entry.scopes:
            payload["scope"] = " ".join(entry.scopes)
        if entry.extra:
            payload.update(entry.extra)
        if provider_lower in _JSON_TOKEN_PROVIDERS:
            response = requests.post(
                token_url, headers={"Content-Type": "application/json"}, json=payload, timeout=30
            )
        else:
            response = requests.post(token_url, data=payload, timeout=30)
        if response.status_code >= 400:
            reason = response.reason or "request failed"
            raise AuthError(f"OAuth refresh failed: {response.status_code} {reason}")
        data = response.json()
        access = data.get("access_token")
        if not access:
            raise AuthError("OAuth refresh response missing access_token")
        refresh = data.get("refresh_token") or entry.refresh
        expires_in = data.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)):
            expires_at = int(time.time() * 1000 + expires_in * 1000)
        entry.access = str(access)
        entry.refresh = str(refresh) if refresh else None
        entry.expires = expires_at
        self._persist_entry(entry_key, entry)
        return str(access)

    def _persist_entry(self, entry_key: str, entry: AuthEntry) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return
        if not isinstance(data, dict):
            return
        value = data.get(entry_key)
        if isinstance(value, dict):
            value["access"] = entry.access
            if entry.refresh:
                value["refresh"] = entry.refresh
            if entry.expires:
                value["expires"] = entry.expires
            data[entry_key] = value
            self.path.write_text(json.dumps(data, indent=2))
