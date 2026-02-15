# Project Brief

## Project
- Name: `deepagents-harness`
- Description: Production-oriented DeepAgents CLI harness with a Textual TUI for interactive coding-agent workflows.

## Core Goals
- Provide a stable terminal-first agent experience via the `deepagents` CLI entrypoint.
- Keep model selection explicit and user-controlled (no implicit fallback model).
- Support multi-provider model execution (OpenAI, Anthropic, Google) with clear credential boundaries.
- Preserve first-class tooling for Morph (`warp_grep`, `fast_apply`) and extension-based integrations.
- Keep persistent memory, thread checkpoints, and skill loading deterministic across sessions.

## Primary Users
- Engineers operating coding agents from a local terminal.
- Power users managing multiple agent profiles, models, extensions, and subagent workflows.

## Project Constraints
- Treat implementation as production-grade, not demo/sandbox.
- Core dependency is pinned to `deepagents==0.4.1` (configured package index source of truth).
- CLI package version (`src/deepagents_cli/_version.py`) remains independent from core dependency version.
- OpenAI should run through Responses API behavior with default `service_tier=priority`.
- File tool paths must remain absolute (enforced in prompt/agent behavior).

## Success Criteria
- `deepagents` starts reliably after setup and can run interactive tasks end-to-end.
- Users can configure/select models explicitly and inspect resolution with `/debug model`.
- Slash commands, approvals, and tool rendering remain predictable in the TUI.
- Memory/skills/extensions load from documented user/project paths without manual patching.
