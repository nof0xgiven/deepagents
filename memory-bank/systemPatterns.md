# System Patterns

## Architecture Overview
- Entry + runtime orchestration: `src/deepagents_cli/main.py`
- Agent construction + middleware/tool wiring: `src/deepagents_cli/agent.py`
- Textual application shell + interaction loop: `src/deepagents_cli/app.py`
- UI adapter from agent events to widgets: `src/deepagents_cli/textual_adapter.py`

## Major Subsystems
- Command system:
  - Registry/context/handlers in `src/deepagents_cli/commands/`
  - Namespaced handlers (`core`, `model`, `assemble`) replace ad-hoc command branching.
- Model system:
  - Catalog + types + state in `model_registry.py`, `model_types.py`, `model_controller.py`, `settings_store.py`
  - Provider instantiation and auth wiring via `config.py`, `provider_adapters.py`, `auth_store.py`
- Extensions:
  - Extension lifecycle in `src/deepagents_cli/extensions.py`
  - Linear integration in `src/deepagents_cli/ext/linear.py`
- UI widgets:
  - Chat, approvals, autocomplete, status, model selector under `src/deepagents_cli/widgets/`

## Data and Control Flow
1. CLI starts in `main.py`, parses args, loads config/tools/sessions.
2. App boots `DeepAgentsApp` and creates agent via `create_cli_agent`.
3. User input enters `ChatInput`; slash command handling is evaluated before normal message submit.
4. Commands dispatch through `CommandRegistry` with `CommandContext`.
5. Agent execution events stream back through `TextualUIAdapter` into message/status widgets.
6. Sessions and memory persist to SQLite-backed stores and configured memory paths.

## Key Technical Decisions
- Explicit model selection is required before task execution.
- OpenAI-compatible execution uses Responses-compatible behavior and service tier defaults.
- Morph tools (`warp_grep`, `fast_apply`) are always registered and delegated via subagents.
- Slash command UX is separated from generic file autocomplete to avoid rendering/clipping conflicts.
- Command handlers are modularized to keep UI app shell smaller and easier to extend.

## Critical Implementation Paths
- Model resolution path:
  - `SettingsStore` -> `ModelRegistry` -> provider config/auth -> adapter instance.
- Slash command path:
  - `ChatInput` slash suggestion/update -> menu navigation/apply -> app command dispatch.
- Memory path:
  - `MemoryMiddleware` sources + backend routing to `/memories/` store namespace.
