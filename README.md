# DeepAgents

An AI coding agent that runs in your terminal. DeepAgents gives you a full TUI — autocomplete, model switching, tool approvals, persistent memory, skills, and multi-model support — built on LangChain and LangGraph. Think of it as a local-first, extensible alternative to cloud-hosted coding assistants, where you own the agent loop and can plug in any LLM provider.

## What it does

You type. The agent reads your codebase, writes code, runs commands, and manages files — all inside a Textual-powered terminal UI. It remembers context across sessions, delegates to subagents for parallel work, and integrates with external tools via MCP servers and extensions.

It supports OpenAI, Anthropic, Google, and any OpenAI-compatible provider. You can switch models mid-conversation, configure reasoning effort, and bring your own API keys.

## Quickstart

```bash
# Install with uv (recommended)
uv pip install -e .

# Or classic pip
pip install -e .

# Run
deepagents
```

On first launch, the model selector opens automatically. Pick a model and start working.

## Configuration

Create `~/.deepagents/.env` for API keys:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

Or use `~/.deepagents/auth.json` for multi-provider setups and OAuth (see `docs/oauth.md`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `DEEPAGENTS_REASONING_EFFORT` | `high` | `none\|low\|medium\|high\|xhigh` |
| `DEEPAGENTS_SERVICE_TIER` | `priority` | OpenAI service tier |
| `DEEPAGENTS_MCP` | `1` | Set `0` to disable MCP tools |
| `DEEPAGENTS_CHROME_MCP` | `1` | Set `0` to disable Chrome DevTools |

## CLI

```bash
deepagents                              # Interactive TUI
deepagents --agent mybot                # Named agent profile (separate memory/skills)
deepagents --model openai:gpt-4o        # Override model
deepagents --reasoning medium           # Override reasoning effort
deepagents --no-auto-approve            # Require tool approvals
```

### In-session commands

| Command | Description |
|---|---|
| `/model` | Open model selector |
| `/model my-alias` | Switch to a model by alias |
| `/debug model` | Inspect resolved model config |
| `/assemble` | Run Linear issue pipeline (scout -> planner -> worker -> reviewer) |
| `/clear` | Clear chat, start new session |
| `/remember` | Persist learnings to memory and skills |
| `/tokens` | Show token usage |
| `/threads` | Show session info |

Type `@` to fuzzy-search project files. Type `/` to browse commands.

## Model selection

The model selector reads from three files in `~/.deepagents/`:

**models.json** — provider catalog:
```json
{
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api": "openai-responses",
      "models": [
        { "id": "gpt-4o", "alias": "primary", "reasoning": "high" }
      ]
    }
  }
}
```

**auth.json** — credentials:
```json
{
  "openai": { "type": "api_key", "key": "sk-..." }
}
```

**settings.json** — defaults:
```json
{
  "model": {
    "active": { "provider": "openai", "id": "gpt-4o" },
    "reasoning": "high",
    "service_tier": "priority"
  }
}
```

See `docs/models.md`, `docs/providers.md`, `docs/settings.md` for full reference.

## Features

- **Terminal UI** built with Textual — keyboard-driven, dark theme, responsive layout
- **Multi-provider** support: OpenAI, Anthropic, Google, and any OpenAI-compatible API
- **Live model switching** via `/model` selector with alias support
- **Tool approval flow** with auto-approve toggle (Shift+Tab)
- **Persistent memory** across sessions via AGENTS.md
- **Skills** — reusable prompt modules loaded from `~/.deepagents/<agent>/skills/`
- **Subagents** for parallel task delegation
- **Extensions** — pluggable Python modules for custom integrations
- **Chrome DevTools MCP** — browse, click, and automate web pages from the agent
- **File autocomplete** — fuzzy `@file` search across git-tracked files
- **Slash commands** — `/assemble`, `/model`, `/clear`, `/remember`, and more
- **Session threads** with checkpoint-based history resumption

## Extensions

Extensions are Python modules that register tools, middleware, or commands. They load from `~/.deepagents/extensions/` and `<project>/.deepagents/extensions/`.

```json
{
  "extensions": ["~/.deepagents/extensions/my_ext.py"],
  "extension_settings": {
    "my_ext": { "log_level": "debug" }
  }
}
```

Built-in: **Linear** (`deepagents_cli.ext.linear:register`) — powers the `/assemble` pipeline.

See `docs/extensions.md` for the full extension API.

## Memory and skills layout

```
~/.deepagents/<agent>/
  AGENTS.md                     # Agent memory and context
  subagents/<name>.md           # Subagent system prompts
  skills/<skill>/SKILL.md       # Reusable skill definitions

<project>/.deepagents/
  AGENTS.md                     # Project-specific agent context
  subagents/<name>.md
  skills/<skill>/SKILL.md
```

## Chrome DevTools

The agent can control Chrome for web automation. It starts `chrome-devtools-mcp` via npx by default.

To attach to your own browser session:

```bash
DEEPAGENTS_CHROME_BROWSER_URL=http://127.0.0.1:9222 deepagents
```

To disable entirely:

```bash
DEEPAGENTS_CHROME_MCP=0 deepagents
```

## License

MIT
