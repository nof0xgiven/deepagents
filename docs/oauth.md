# OAuth

DeepAgents supports OAuth credentials in `~/.deepagents/auth.json`.

## OAuth entry format

```json
{
  "provider-name": {
    "type": "oauth",
    "access": "<access-token>",
    "refresh": "<refresh-token>",
    "expires": 1700000000000,
    "token_url": "https://.../token",
    "client_id": "...",
    "client_secret": "...",
    "scopes": ["scope-a", "scope-b"]
  }
}
```

Notes:
- `expires` is epoch milliseconds.
- If the token is expired and `refresh` + `token_url` are present, DeepAgents
  will refresh automatically.
- If `token_url` is missing, DeepAgents will refuse to use expired tokens.

To use OAuth for a provider, point its `auth` to the OAuth entry in
`models.json` or `settings.json`.

## API keys

For API key auth, use:

```json
{
  "provider-name": { "type": "api_key", "key": "sk-..." }
}
```
