# AGENTS

## Project
DeepAgents CLI harness configured for gpt-5.2-codex. The entrypoint is the `deepagents` CLI.

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
Required in `.env`:
- OPENAI_API_KEY
- LANGSMITH_API_KEY
- MORPH_API_KEY

See README.md for the full list of optional overrides.

## Repo Layout
- src/deepagents_cli/ — main package
- README.md — usage and configuration

## Tests
No repo test runner is documented in README.md.

## Memory + Skills
Memory and skills live in:
- ~/.deepagents/<agent>/
- <project>/.deepagents/
