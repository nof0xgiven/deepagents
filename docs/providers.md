# Providers

DeepAgents uses a provider registry to route model calls to the right API
implementation. Providers are defined in `~/.deepagents/models.json` (and can be
partially overridden in `~/.deepagents/settings.json`).

## Provider fields

Each provider entry supports:

- `base_url`: Base API URL (optional; defaults to the SDK default).
- `api`: Which protocol to use:
  - `openai-responses`
  - `openai-completions`
  - `anthropic-messages`
  - `google-generative-ai`
- `headers`: Extra headers to attach to every request (optional).
- `api_key` / `apiKey`: Inline key (optional, prefer `auth` or `auth.json`).
- `auth`: Where credentials are resolved from (optional):
  - `{ "source": "auth_json", "key": "openai" }`
  - `{ "source": "env", "key": "OPENAI_API_KEY" }`
  - `{ "source": "inline", "key": "sk-..." }`
  - or a string: env var if it looks like `OPENAI_API_KEY`, otherwise an auth.json key
- `compat`: Provider-specific behavior flags (optional).

## Example

```json
{
  "providers": {
    "example": {
      "base_url": "https://api.example.com/v1",
      "api": "openai-responses",
      "auth": { "source": "auth_json", "key": "example" }
    }
  }
}
```

## API protocol notes

- `openai-responses`: OpenAI Responses API (reasoning + tool calling).
- `openai-completions`: OpenAI-compatible chat/completions APIs.
- `anthropic-messages`: Anthropic Messages API.
- `google-generative-ai`: Gemini API via Google Generative AI.

Some OAuth flows require extra headers; set them in `headers` if needed.

See `docs/models.md` for model fields.
