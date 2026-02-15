# Technical Context

## Stack
- Language: Python `>=3.11,<4.0`
- Packaging: setuptools (`pyproject.toml`)
- UI framework: Textual
- Agent runtime: DeepAgents (`deepagents==0.4.1`)
- LLM integrations: LangChain adapters for OpenAI, Anthropic, Google
- Persistence: SQLite (`sessions.db`, `store.db`) with checkpoint/store abstractions

## Key Dependencies
- `deepagents==0.4.1`
- `langchain`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`
- `langchain-mcp-adapters`, `mcp`
- `langgraph-checkpoint-sqlite`, `aiosqlite`
- `textual`, `textual-autocomplete`, `rich`, `prompt-toolkit`
- Integration/runtime helpers: `daytona`, `modal`, `runloop-api-client`, `requests`

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
deepagents
```

## Environment Configuration
- Required keys in repo `.env` or `~/.deepagents/.env`:
  - `OPENAI_API_KEY`
  - `LANGSMITH_API_KEY`
  - `MORPH_API_KEY`
- Common optional keys:
  - `ANTHROPIC_API_KEY`
  - `GOOGLE_API_KEY`
  - `TAVILY_API_KEY`
- Runtime overrides:
  - `DEEPAGENTS_REASONING_EFFORT`
  - `DEEPAGENTS_SERVICE_TIER`
  - `DEEPAGENTS_MCP`, `DEEPAGENTS_CHROME_MCP`, and related Chrome MCP settings

## Storage and Config Paths
- Models: `~/.deepagents/models.json`
- Provider credentials: `~/.deepagents/auth.json`
- Settings: `~/.deepagents/settings.json` and `<project>/.deepagents/settings.json`
- User memory/skills: `~/.deepagents/<agent>/`
- Project memory/skills: `<project>/.deepagents/`
- Sessions checkpoint DB: `~/.deepagents/sessions.db`
- Persistent store DB: `~/.deepagents/store.db`

## Constraints and Gaps
- No formal repo test runner is documented in README.
- Validation currently relies on targeted runtime checks and compile/import checks.
- Extensions are trusted in-process code and must be treated as production-impacting.
