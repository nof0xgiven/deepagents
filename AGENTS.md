# AGENTS

## Project
DeepAgents CLI harness. The entrypoint is the `deepagents` CLI.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run
```bash
deepagents
# Example override
DEEPAGENTS_REASONING_EFFORT=high deepagents
```

## Environment
Required in `.env` (already present in this repo or in ~/.deepagents/.env):
- OPENAI_API_KEY
- LANGSMITH_API_KEY
- MORPH_API_KEY

Optional API keys:
- ANTHROPIC_API_KEY
- GOOGLE_API_KEY
- TAVILY_API_KEY

Optional overrides:
- OPENAI_MODEL
- DEEPAGENTS_SERVICE_TIER (default: priority)
- DEEPAGENTS_REASONING_EFFORT (default: high; allowed: none|low|medium|high|xhigh)
- DEEPAGENTS_LANGSMITH_PROJECT (route agent traces to a dedicated project)
- DEEPAGENTS_MCP (default: 1; set to 0 to disable all MCP tools)
- DEEPAGENTS_CHROME_MCP (default: 1; set to 0 to disable Chrome DevTools MCP)
- DEEPAGENTS_CHROME_BROWSER_URL
- DEEPAGENTS_CHROME_WS_ENDPOINT
- DEEPAGENTS_CHROME_AUTOCONNECT (default: 1)
- DEEPAGENTS_CHROME_CHANNEL
- DEEPAGENTS_CHROME_MCP_COMMAND (default: npx)
- DEEPAGENTS_CHROME_MCP_PACKAGE (default: chrome-devtools-mcp@latest)
- DEEPAGENTS_CHROME_MCP_ARGS

See README.md for additional notes.

## Core versioning notes
- Source of truth for deepagents is the configured package index used by this repo, not public PyPI.
- Current core dependency pin: deepagents==0.4.1 (from the configured index; PyPI lists 0.3.12 as latest).
- Keep the CLI version (`src/deepagents_cli/_version.py`) independent from the core dependency version.

## Feature intent (do not regress)
- Model selection is explicit. No implicit fallback when no model is configured.
- OpenAI uses Responses API with service_tier defaulting to `priority`.
- Morph tools are first-class: `warp_grep` and `fast_apply` are always registered and get dedicated subagents.
- File tool paths must be absolute (system prompt enforces this).

## Repo Layout
- src/deepagents_cli/ — main package
- README.md — usage and configuration

## Tests
No repo test runner is documented in README.md.

## Memory + Skills
Memory and skills live in:
- ~/.deepagents/<agent>/
- <project>/.deepagents/

## Prompt + memory locations
- Base system prompt template (immutable): src/deepagents_cli/default_agent_prompt.md
- Base template source of truth: src/deepagents_cli/default_agent_prompt.md
- Project override for base prompt: <project>/.deepagents/system.md (or SYSTEM.md) if present
- Per-agent memory instructions: ~/.deepagents/<agent>/AGENTS.md
- Project memory overlay: <project>/.deepagents/AGENTS.md
- Provider + model config: ~/.deepagents/models.json
- Provider credentials: ~/.deepagents/auth.json
- Settings (defaults + active model): ~/.deepagents/settings.json and <project>/.deepagents/settings.json
- Session checkpoints (threads): ~/.deepagents/sessions.db (SQLite)
- Persistent store (cross-thread memory): ~/.deepagents/store.db (SQLite)
- Persistent memory namespace: /memories/ (use file tools to read/write long-term notes)
- Input history: ~/.deepagents/history.jsonl
- Skills:
  - ~/.deepagents/<agent>/skills/
  - <project>/.deepagents/skills/

## Subagent skills configuration
- Subagent config file (project override): <project>/.deepagents/subagents/<subagent>/AGENTS.md
- Subagent config file (user fallback): ~/.deepagents/<agent>/subagents/<subagent>/AGENTS.md
- Define allowed skills in YAML frontmatter, e.g.
  ---
  skills:
    - web-research
    - code-review
  ---
- Skill names resolve from project skills first, then user skills. Only listed skills are exposed to that subagent.

## Extensions
- Auto-discovered from:
  - ~/.deepagents/extensions/
  - <project>/.deepagents/extensions/
- Explicit extensions can be listed in ~/.deepagents/settings.json under "extensions"
- Per-run overrides:
  - --extensions (repeatable; accepts path or module:func)
  - --extensions-only (skip auto-discovery)
  - --no-extensions (disable all extensions)
- Extension settings overrides live in ~/.deepagents/settings.json under "extension_settings"
- Extensions can register tools, middleware, subagents, prompt additions, and event hooks
- Docs: docs/extensions.md

## Codex Memory Bank
I maintain a persistent Memory Bank in `memory-bank/` so project context survives across sessions.

### Required Files
- `memory-bank/projectbrief.md`
- `memory-bank/productContext.md`
- `memory-bank/systemPatterns.md`
- `memory-bank/techContext.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`

### Read Order
1. `projectbrief.md`
2. `productContext.md`
3. `systemPatterns.md`
4. `techContext.md`
5. `activeContext.md`
6. `progress.md`

### Operating Rules
- Read all memory-bank files at the start of each task.
- Update memory-bank docs after significant implementation changes.
- When asked to "update memory bank", review every memory-bank file before editing.
- Keep entries concise, factual, and aligned with current repo state.
