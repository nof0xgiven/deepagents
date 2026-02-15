# Product Context

## Why This Project Exists
- The base DeepAgents stack is flexible but needs a concrete, opinionated CLI harness for daily engineering work.
- Users need a repeatable way to run agent sessions with memory, skills, tools, and model/provider controls without rebuilding configuration each time.

## Problems It Solves
- Reduces setup friction for interactive coding-agent sessions.
- Centralizes model/provider configuration and runtime overrides.
- Provides persistent context via sessions and memory storage across CLI runs.
- Enables extension-driven capability growth (tools, middleware, subagents, commands).

## How It Should Work (User Perspective)
- User installs once, runs `deepagents`, and immediately lands in a working TUI session.
- If no model is active, the UI blocks execution and prompts model selection.
- User can run slash commands (`/help`, `/model`, `/assemble`, etc.) from the main input.
- Tool usage and approvals are visible, controllable, and auditable in-session.
- Session history and memory are resumable across runs.

## UX Goals
- Fast-to-understand interface with clear command discoverability.
- Deterministic behavior for command handling and model switching.
- Minimal surprise around approvals, tool calls, and status indicators.
- Graceful handling when optional integrations are unavailable (for example disabled MCP providers).

## Key User Workflows
- Bootstrap environment and run `deepagents`.
- Select or switch model from command or selector UI.
- Execute coding tasks with tools/extensions/subagents.
- Resume prior thread context and memory-backed work.
- Use extension commands like `/assemble` when enabled.
