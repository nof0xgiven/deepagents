# DeepAgents CLI Harness

This repo packages a configured DeepAgents CLI so you can run `deepagents` in your terminal and start an interactive session.

## Quickstart

```bash
# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Run (auto-approve on by default)
deepagents
```

## Environment

Recommended in `~/.deepagents/.env` (user-local) for simple environment-based auth:

```bash
# API keys
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...

# Defaults
DEEPAGENTS_REASONING_EFFORT=high
DEEPAGENTS_SERVICE_TIER=priority
```

For multi-provider setups or OAuth, use `~/.deepagents/auth.json`
(see `docs/oauth.md`).

Required in repo `.env` (already present in this repo):

- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`
- `MORPH_API_KEY`

Optional overrides:

- `OPENAI_MODEL`
- `DEEPAGENTS_SERVICE_TIER` (default: `priority`)
- `DEEPAGENTS_REASONING_EFFORT` (default: `high`; allowed: `none|low|medium|high|xhigh`)
- `DEEPAGENTS_MCP` (default: `1`; set to `0` to disable all MCP tools)
- `DEEPAGENTS_CHROME_MCP` (default: `1`; set to `0` to disable Chrome DevTools MCP)
- `DEEPAGENTS_CHROME_BROWSER_URL` (connect to an existing Chrome with remote debugging)
- `DEEPAGENTS_CHROME_WS_ENDPOINT` (connect to an existing Chrome via DevTools WS endpoint)
- `DEEPAGENTS_CHROME_AUTOCONNECT` (default: `1`; auto-connect to a running Chrome)
- `DEEPAGENTS_CHROME_CHANNEL` (optional channel for auto-connect, e.g. `beta`)
- `DEEPAGENTS_CHROME_MCP_COMMAND` (default: `npx`)
- `DEEPAGENTS_CHROME_MCP_PACKAGE` (default: `chrome-devtools-mcp@latest`)
- `DEEPAGENTS_CHROME_MCP_ARGS` (extra args passed to the MCP server)

## CLI

```bash
# Start interactive TUI
deepagents

# Use a specific agent profile (separate memory/skills)
deepagents --agent mybot

# Override model (by alias or provider:model-id)
deepagents --model provider:model-id

# Override reasoning/service tier
deepagents --reasoning medium --service-tier priority

# Require approvals
deepagents --no-auto-approve
```

### Model selection

Use `/model` to open the selector and switch models inside the TUI. If no active
model is configured, the selector opens automatically and the agent will block
until you choose one.

```text
/model
/model
/model my-alias
```

Use `/debug model` to inspect the resolved model selection (settings, allow-list,
and catalog resolution).

The selector reads `~/.deepagents/models.json` (providers + models), credentials
from `~/.deepagents/auth.json`, and defaults from `~/.deepagents/settings.json`.
Use `alias` to name entries and select them by alias.

Example `~/.deepagents/models.json`:

```json
{
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
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

Example `~/.deepagents/auth.json`:

```json
{
  "openai": { "type": "api_key", "key": "sk-..." }
}
```

Example `~/.deepagents/settings.json`:

```json
{
  "model": {
    "active": { "provider": "openai", "id": "model-id" },
    "reasoning": "high",
    "service_tier": "priority"
  }
}
```

Compatibility keys (optional):

```json
{
  "defaultProvider": "provider-name",
  "defaultModel": "model-id",
  "defaultThinkingLevel": "high",
  "enabledModels": ["provider/model-id"]
}
```

Additional docs:
- `docs/providers.md`
- `docs/models.md`
- `docs/oauth.md`
- `docs/settings.md`

## Features

- **DeepAgents CLI** with TUI, threads, skills, and persistent memory (AGENTS.md)
- **OpenAI Responses API** when configured, with `service_tier` support
- **Subagents** for parallel delegation
- **Skills** via `~/.deepagents/<agent>/skills/` and `<project>/.deepagents/skills/`
- **Morph tools**: `warp_grep`, `fast_apply`
- **Extensions** loaded from `~/.deepagents/extensions/` and `<project>/.deepagents/extensions/`
- **/assemble** Linear pipeline (scout -> planner -> worker -> reviewer) when the Linear extension is enabled
- **Chrome DevTools MCP tools** (prefixed with `chrome_`)

## Extensions

Detailed extension documentation lives at `docs/extensions.md`.

### Getting started

Create `~/.deepagents/settings.json` and list any explicit extensions:

```json
{
  "extensions": [
    "~/.deepagents/extensions/my_ext.py",
    "/absolute/path/to/other_ext"
  ],
  "extension_settings": {
    "my_ext": {
      "log_level": "debug"
    }
  }
}
```

Run with explicit-only loading if you want to skip auto-discovery:

```bash
deepagents --extensions-only
```

Built-in extension modules:
- Linear: `deepagents_cli.ext.linear:register`

### /assemble prompts

`/assemble` uses subagent prompts from `~/.deepagents/<agent>/subagents/` or
`<project>/.deepagents/subagents/`.

## Memory + Skills Layout

```
~/.deepagents/<agent>/
  ├── AGENTS.md
  ├── subagents/
  │   └── <name>.md or <name>/SYSTEM.md
  └── skills/
      └── <skill>/SKILL.md

<project>/.deepagents/
  ├── AGENTS.md
  ├── subagents/
  │   └── <name>.md or <name>/SYSTEM.md
  └── skills/
      └── <skill>/SKILL.md
```

## Notes

- The CLI uses DeepAgents middleware for memory and skills.
- Model selection is explicit; configure a model before running tasks.
- Reasoning effort defaults to `high` but can be overridden per run.

## Chrome DevTools MCP (Headless)

The CLI will start `chrome-devtools-mcp` via `npx` by default and add its tools
(prefixed with `chrome_`) to the agent. If you want to attach to an existing
Chrome session so the agent can see your current tabs, launch Chrome with remote
debugging and set `DEEPAGENTS_CHROME_BROWSER_URL`:

```bash
DEEPAGENTS_CHROME_BROWSER_URL=http://127.0.0.1:9222 deepagents
```

If you have Chrome configured for auto-connect, you can enable it with:

```bash
DEEPAGENTS_CHROME_AUTOCONNECT=1 DEEPAGENTS_CHROME_CHANNEL=beta deepagents
```

To disable Chrome DevTools MCP entirely:

```bash
DEEPAGENTS_CHROME_MCP=0 deepagents
```
