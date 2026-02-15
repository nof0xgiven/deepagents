# Settings

DeepAgents reads settings from:

- Global: `~/.deepagents/settings.json`
- Project: `<project>/.deepagents/settings.json`

Project settings override global settings via deep-merge (arrays replace).

## Model selection

```json
{
  "model": {
    "active": { "provider": "openai", "id": "model-id" },
    "reasoning": "high",
    "service_tier": "priority"
  }
}
```

The `active` field may be a string alias (from `models.json`) or an object with
`provider` + `id`. You can also include `api` and `base_url` for one-off
overrides. If no active model is set, the TUI will force `/model`.

Use `/debug model` in the TUI to print the resolved model selection.

## Compatibility keys

The settings loader also understands these alternative keys:

```json
{
  "defaultProvider": "provider-name",
  "defaultModel": "model-id",
  "defaultThinkingLevel": "high",
  "enabledModels": [
    "provider/model-id",
    "provider:model-id"
  ]
}
```

When present, `defaultProvider` + `defaultModel` are used as the active model if
`model.active` is not set. `defaultThinkingLevel` maps to `model.reasoning`, and
`enabledModels` filters the model selector to the listed entries.

You can also define the allow-list directly under `model.enabled`.

## Provider overrides

```json
{
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api": "openai-responses",
      "auth": { "source": "auth_json", "key": "openai" }
    }
  }
}
```
