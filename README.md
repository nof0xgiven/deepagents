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
DEEPAGENTS_REASONING_EFFORT=high deepagents
```

## Environment

Required in `.env` (already present in this repo):

- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`
- `MORPH_API_KEY`

Optional overrides:

- `OPENAI_MODEL` (default: `gpt-5.2-codex`)
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

# Override model (provider auto-detected)
deepagents --model gpt-5.2-codex

# Override reasoning/service tier
deepagents --reasoning medium --service-tier priority

# Require approvals
deepagents --no-auto-approve
```

## Features

- **DeepAgents CLI** with TUI, threads, skills, and persistent memory (AGENTS.md)
- **OpenAI Responses API** for `gpt-5.2-codex`, with required `service_tier=priority`
- **Subagents** for parallel delegation
- **Skills** via `~/.deepagents/<agent>/skills/` and `<project>/.deepagents/skills/`
- **Morph tools**: `warp_grep`, `fast_apply`
- **Chrome DevTools MCP tools** (prefixed with `chrome_`)

## Memory + Skills Layout

```
~/.deepagents/<agent>/
  ├── AGENTS.md
  └── skills/
      └── <skill>/SKILL.md

<project>/.deepagents/
  ├── AGENTS.md
  └── skills/
      └── <skill>/SKILL.md
```

## Notes

- The CLI uses DeepAgents middleware for memory and skills.
- The default model is `gpt-5.2-codex` with Responses API enabled.
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
