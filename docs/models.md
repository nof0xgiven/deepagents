# Models

Models live under providers in `~/.deepagents/models.json`. Each model inherits
provider defaults (api, base_url, headers) and may override them.

If you use a top-level `models` array instead of provider nesting, include a
`provider` field for each model.

## Model fields

- `id` (required): Provider-specific model ID.
- `name` (optional): Display name in the UI.
- `alias` (optional): Short selection alias for `/model`.
- `api` (optional): Override provider `api` for this model.
- `base_url` (optional): Override provider base URL for this model.
- `reasoning` (optional): `true|false|"low"|"medium"|"high"|"xhigh"`.
- `service_tier` (optional): OpenAI service tier (e.g., `priority`).
- `input` (optional): Supported input types (e.g., `"text"`, `"image"`).
- `max_tokens` (optional): Max output tokens.
- `context_window` (optional): Max context size.
- `compat` (optional): Provider-specific flags.

CamelCase equivalents are also accepted for compatibility:
`baseUrl`, `apiKey`, `serviceTier`, `maxTokens`, `contextWindow`, `authEnv`.

If `compat.serviceTier` is set, it is treated as `service_tier`.

## Example

```json
{
  "providers": {
    "openai": {
      "api": "openai-responses",
      "models": [
        {
          "id": "model-id",
          "name": "Primary",
          "alias": "primary",
          "reasoning": "high",
          "service_tier": "priority"
        }
      ]
    }
  }
}
```
