# Extensions

DeepAgents CLI supports pluggable Python extensions that can register tools, middleware,
subagents, prompt additions, and lifecycle event hooks.

## Discovery and precedence

Extensions are discovered in the following order, with later entries overriding earlier
entries when names collide:

1. Auto-discovered user extensions: `~/.deepagents/extensions/`
2. Auto-discovered project extensions: `<project>/.deepagents/extensions/`
3. Explicit list from `~/.deepagents/settings.json` under `extensions`
4. CLI `--extensions` entries

Use `--extensions-only` to skip auto-discovery and only load explicit entries.
Use `--no-extensions` to disable all extensions.

## Supported layouts

### Single file

Place a Python file directly in an auto-discovery folder:

- `~/.deepagents/extensions/my_ext.py`
- `<project>/.deepagents/extensions/my_ext.py`

The file must export a `register(api)` function.

### Directory with `index.py`

If a directory contains `index.py`, it is treated as an extension with a `register(api)`
entrypoint:

- `~/.deepagents/extensions/my_ext/index.py`

### Directory with `extension.json`

Use a manifest to specify entrypoint and config:

`extension.json`:
```json
{
  "name": "my_ext",
  "entrypoint": "index.py:register",
  "enabled": true,
  "config": {
    "log_level": "info"
  }
}
```

`entrypoint` accepts:
- `path.py:func` relative to the extension directory
- `package.module:func` (imported via Python)

## Settings file

Global settings live at `~/.deepagents/settings.json`:

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

`extension_settings` overrides are merged first, then inline config (manifest or explicit
entry config) overwrites the same keys.

## Extension API

Each extension exports a `register(api)` entrypoint and may call:

- `api.register_tool(tool)` – add a tool (callable or `BaseTool`)
- `api.register_middleware(middleware)` – add `AgentMiddleware`
- `api.register_subagent(spec)` – add a subagent spec
- `api.register_prompt(text)` – append text to the system prompt
- `api.on(event, handler)` – register event hooks
- `api.get_store()` – access the persistent store (may be `None`)
- `api.get_backend()` – access the composite backend
- `api.get_project_root()` – access project root (may be `None`)
- `api.config` – merged config dict for this extension

### Subagent specs

`register_subagent` accepts a dict with these keys:

- `name` (required)
- `description` (recommended)
- `system_prompt` (recommended)
- `tools` (list of tools)
- `skills` (optional list of skill directories)

If `skills` is omitted, the CLI attempts to resolve it from:
`<project>/.deepagents/subagents/<name>/AGENTS.md` or
`~/.deepagents/<agent>/subagents/<name>/AGENTS.md` using YAML frontmatter.

## Events

Available events:

- `session_start` – payload: `{ "state": ... }`
- `session_end` – payload: `{ "state": ... }`
- `tool_call` – payload: `{ "tool_call": ..., "tool_name": ... }`
- `tool_result` – payload: `{ "tool_call": ..., "tool_name": ..., "result": ... }`
- `agent_response` – payload: `{ "response": ... }`

Handlers receive `(payload, context)` where `context` includes:
`extension_name`, `config`, `assistant_id`, `project_root`, `store`, `backend`, and
`runtime` when available.

Async event handlers are supported in async execution contexts. If an async handler is
registered but runs in a sync context, it is skipped with a warning.
Async `register(...)` entrypoints are not supported.

## Operational notes

- Extensions execute in-process with full local permissions. Treat extension code as
  trusted.
- Extension code always runs locally, even if the agent backend is a remote sandbox.
- Restart the CLI to reload extensions; there is no hot-reload.

## Built-in extensions

### Linear

The CLI ships a built-in Linear extension module:

- `deepagents_cli.ext.linear:register`

Enable it via `~/.deepagents/settings.json`:

```json
{
  "extensions": ["deepagents_cli.ext.linear:register"]
}
```

Or for a single run:

```bash
deepagents --extensions deepagents_cli.ext.linear:register
```

The Linear extension reads `LINEAR_API_KEY` (or `~/.deepagents/auth.json`) and
uses `https://api.linear.app/graphql` by default. You can override the endpoint with
`LINEAR_API_URL` if needed.

Example `~/.deepagents/auth.json`:

```json
{
  "linear": {
    "apiKey": "lin_api_..."
  }
}
```

### /assemble

When the Linear extension is enabled, the CLI exposes a `/assemble` command:

```text
/assemble TEAM-123 [--no-comments] [--max-comments=N] [--no-comment]
```

It fetches the issue (and optional comments), optionally posts "Assembly started",
and sends a structured prompt that instructs the agent to run a
`scout -> planner -> worker -> reviewer` pipeline using the `task` tool.
After each phase, the agent should post progress via `linear_comment`.

#### Assemble subagents

The CLI auto-registers the following subagent types for `/assemble`:

- `scout`
- `planner`
- `worker`
- `reviewer`

Subagent prompts are loaded from the first matching path in this order:

1. `<project>/.deepagents/subagents/<name>.md`
2. `<project>/.deepagents/subagents/<name>/SYSTEM.md`
3. `~/.deepagents/<agent>/subagents/<name>.md`
4. `~/.deepagents/<agent>/subagents/<name>/SYSTEM.md`

If no custom prompt is found, built-in defaults are used.
