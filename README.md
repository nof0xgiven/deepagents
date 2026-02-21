# DeepAgents CLI

> **Status: Alpha** — actively developed, things will break and change.

<image src="image.png" />

## What this is

[Deep Agents](https://github.com/langchain-ai/deepagents) is an open-source agent framework by LangChain. It gives you a planning tool, a virtual filesystem, subagent spawning, and persistent memory — the architectural patterns behind tools like Claude Code and Deep Research, packaged as a Python library.

What it doesn't give you is a way to actually *use* it day-to-day. There's no terminal UI, no model switching, no way to plug in your Anthropic or Google credentials, no OAuth, no plugin system, and no MCP integration. The base library is a foundation — you're expected to build the rest yourself.

**This repo is the rest.**

We (Claude decided it was a collaborative "we" 😁) built a full terminal interface and configuration layer on top of `deepagents==0.4.1`, turning it from a framework into a usable coding agent. Everything here is additive — we don't fork or patch deepagents, we import it as a dependency and layer our code on top. When LangChain ships `0.5.0`, you bump the version and our additions should carry forward.

### What we added

| Layer | What it does | Why it's needed |
|---|---|---|
| **Terminal UI** | Full Textual TUI with chat, streaming, tool approvals, slash commands, autocomplete | deepagents has no interface — it's a library, not an app |
| **Multi-provider auth** | API keys, OAuth tokens, and credential rotation for OpenAI, Anthropic, Google | deepagents uses `init_chat_model` — you wire up auth yourself |
| **Model registry** | Catalog system with live switching, aliases, reasoning effort, service tiers | No built-in way to manage or switch models at runtime |
| **Provider adapters** | Wrappers for OpenAI Responses API, Anthropic Messages, Google Generative AI | deepagents is model-agnostic but you write the glue code |
| **OAuth support** | Use your existing Claude Pro/Max or Google AI Studio subscription | Base library only supports API keys via environment variables |
| **Extensions** | Plugin system for custom tools, middleware, subagents, and hooks | deepagents is extendable but has no plugin architecture |
| **MCP integration** | Chrome DevTools, external tool servers via Model Context Protocol | Not included in base deepagents |
| **Command system** | `/model`, `/assemble`, `/clear`, `/remember`, `/tokens` and more | No CLI command framework in base library |
| **Background subagents** | Non-blocking `task` execution (`check_task`, `wait_for_task`) with a live running-agent pill in the TUI | Base flow blocks on subagent completion and has no built-in activity badge |
| **Linear integration** | `/assemble` pipeline: scout -> planner -> worker -> reviewer on Linear issues | Domain-specific workflow not in base library |
| **Session management** | Thread persistence, checkpoint resumption, conversation history | deepagents provides checkpointing primitives but no session UX |

### What we didn't change

The base `deepagents` package is a clean dependency. We call `create_deep_agent()`, use its `CompositeBackend`, `MemoryMiddleware`, `SkillsMiddleware`, and subagent system exactly as designed. No monkey-patching, no forks. Our code lives entirely in the `deepagents_cli` package.

```
deepagents (LangChain)          <-- agent loop, planning, filesystem, subagents
    ↑
deepagents_cli (this repo)      <-- TUI, auth, models, extensions, commands, MCP
```

## Quickstart

```bash
# Install with uv (recommended)
uv pip install -e .

# Or classic pip
pip install -e .

# Run
deepagents
```

On first launch, the model selector opens. Pick a provider, enter credentials, start working.

## Configuration

### API keys

Create `~/.deepagents/.env`:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

### OAuth (use your existing Pro/Max plan)

For Anthropic Claude or Google, you can authenticate via OAuth instead of API keys. This lets you use your existing subscription without separate API billing.

See `docs/oauth.md` for setup. Credentials are stored in `~/.deepagents/auth.json`.

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
deepagents --model openai:gpt-5.2        # Override model
deepagents --reasoning medium           # Override reasoning effort
deepagents --no-auto-approve            # Require tool approvals
```

### In-session commands

| Command | Description |
|---|---|
| `/model` | Open model selector |
| `/model my-alias` | Switch to a model by alias |
| `/debug model` | Inspect resolved model config |
| `/assemble` | Run Linear issue pipeline |
| `/clear` | Clear chat, start new session |
| `/remember` | Persist learnings to memory and skills |
| `/tokens` | Show token usage |
| `/threads` | Show session info |

Type `@` to fuzzy-search project files. Type `/` to browse commands.

## Model selection

The model selector reads from `~/.deepagents/`:

**models.json** — provider catalog:
```json
{
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api": "openai-responses",
      "models": [
        { "id": "gpt-5.2", "alias": "primary", "reasoning": "high" }
      ]
    },
    "anthropic": {
      "api": "anthropic-messages",
      "models": [
        { "id": "claude-sonnet-4-5-20250929", "alias": "sonnet" }
      ]
    }
  }
}
```

**auth.json** — credentials (API key or OAuth):
```json
{
  "openai": { "type": "api_key", "key": "sk-..." },
  "anthropic": { "type": "oauth", "access_token": "...", "refresh_token": "..." }
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

See `docs/models.md`, `docs/providers.md`, `docs/oauth.md`, `docs/settings.md`.
Background subagent behavior is documented in `docs/background-tasks.md`.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Terminal UI (Textual)                          │
│  Chat, approvals, model selector, status bar    │
├─────────────────────────────────────────────────┤
│  Command System        Extensions / Plugins     │
│  /model /assemble      Linear, custom hooks     │
├─────────────────────────────────────────────────┤
│  Auth Store            Model Registry           │
│  OAuth, API keys       Catalog, switching       │
├─────────────────────────────────────────────────┤
│  Provider Adapters     MCP Integration          │
│  OpenAI, Anthropic,    Chrome DevTools,         │
│  Google, compatible    external servers          │
├─────────────────────────────────────────────────┤
│  deepagents 0.4.1 (LangChain)                  │
│  Agent loop, planning, filesystem, subagents,   │
│  memory middleware, skills middleware            │
├─────────────────────────────────────────────────┤
│  LangChain / LangGraph                          │
└─────────────────────────────────────────────────┘
```

Everything above the `deepagents` layer is this repo. Everything below is upstream.

## Upgrading deepagents

This repo pins `deepagents==0.4.1` in `pyproject.toml`. To upgrade:

1. Bump the version in `pyproject.toml`
2. Check `agent.py` — it's the main integration point that calls `create_deep_agent()`
3. Run the app, verify middleware and subagents still work
4. Our config, auth, UI, and extensions layers are independent and shouldn't need changes

The coupling points are: `create_deep_agent()` signature, `CompositeBackend` protocol, `MemoryMiddleware` / `SkillsMiddleware` interfaces, and the subagent parameter format. If LangChain changes those, `agent.py` needs updating. Everything else is decoupled.

## Extensions

Extensions are Python modules that register tools, middleware, or commands:

```json
{
  "extensions": ["~/.deepagents/extensions/my_ext.py"],
  "extension_settings": {
    "my_ext": { "log_level": "debug" }
  }
}
```

Built-in: **Linear** (`deepagents_cli.ext.linear:register`) — powers `/assemble`.

See `docs/extensions.md` for the full extension API.

## Memory and skills

```
~/.agents/skills/
  <skill>/SKILL.md             # Shared default skills

~/.deepagents/<agent>/
  AGENTS.md                     # Agent memory and context
  subagents/<name>.md           # Subagent system prompts
  skills/<skill>/SKILL.md       # Agent-scoped skills (override default)

<project>/.deepagents/
  AGENTS.md                     # Project-scoped context
  subagents/<name>.md
  skills/<skill>/SKILL.md       # Project-scoped skills (highest priority)
```

Skill precedence when names conflict: `<project>/.deepagents/skills` > `~/.deepagents/<agent>/skills` > `~/.agents/skills`.

## Alpha status

This is alpha software. Expect:

- Breaking changes between versions
- Incomplete error handling in edge cases
- UI rough edges
- Provider-specific quirks (especially OAuth token refresh)

What works well: the core agent loop (thanks to deepagents), model switching, tool approvals, session persistence, and the extension system. What's still rough: onboarding UX, documentation, and some provider edge cases.

Contributions and bug reports welcome.

## License

MIT
