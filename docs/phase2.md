# Phase 2: UI Plugin Surface + Plan Mode

This phase adds a UI extension surface so tools like the Pi `questionnaire` can
render rich interactive experiences, and introduces a first‑class “Plan Mode”
that supports safe read‑only planning with explicit execution steps.

## Goals

- Provide a stable, versioned UI plugin API for extensions.
- Enable interactive tools (multi‑question forms, confirmations, wizards).
- Add Plan Mode: read‑only exploration + explicit execution steps with progress.
- Maintain modularity so core deepagents updates do not break extensions.

## Non‑goals

- Re‑implement Pi’s TUI feature set 1:1.
- Add browser UI or remote front‑ends in this phase.
- Build a general plugin marketplace.

## Problem statement

Current extensions can register tools and middleware, but have no way to render
interactive UI. This blocks rich tools like `questionnaire.ts` and makes Plan
Mode UI/flow difficult.

## Proposed UI plugin surface (v1)

### Core concepts

**UIContext**
- A stable interface exposed to extensions that can render interactive widgets
  in the Textual UI.
- Provided only when the session is interactive; returns a structured error
  when the CLI is running in non‑interactive mode (e.g., headless usage).

**UIResult**
- A typed result returned to the tool call, with `cancelled` support and
  structured data.

### Minimal v1 API

```text
ui.select(prompt, options, allow_other=False) -> { value, label, cancelled }
ui.multi_select(prompt, options, allow_other=False) -> { values[], cancelled }
ui.form(questions[]) -> { answers[], cancelled }
ui.confirm(prompt) -> { confirmed }
ui.notify(message, level="info")
```

**Questions schema (form):**
- `id` (string, required)
- `label` (short tab label, optional)
- `prompt` (string, required)
- `options` (list of { value, label, description? })
- `allow_other` (bool, default true)

### Extension API exposure

Expose `ctx.ui` to tool execution similar to Pi’s extension API:

```text
tool.execute(params, ctx)
  ctx.ui -> UIContext (if interactive)
```

When `ctx.ui` is unavailable:
- the tool must return a structured error
- never block the session or crash

### Versioning

- Add `ui_api_version` to extension context.
- Pin behavior with feature flags for breaking changes.

## Questionnaire tool design

Port Pi’s `questionnaire` to a DeepAgents extension tool:

- Uses `ui.form(...)` for multi‑question workflows.
- Supports single‑question fast path (`ui.select`).
- Returns `{ questions, answers, cancelled }`.
- Optional `allow_other` for free‑text entry.

## Plan Mode design

### Behavior

- **Read‑only mode** for planning: only safe tools are available.
- **Execution mode** for implementing the plan steps.
- User toggles with `/plan` (command) or a UI toggle.
- The agent outputs a numbered plan under a `Plan:` header.
- During execution, steps are marked with `[DONE:n]`.

### Tool policy

When Plan Mode is enabled:
- Allow: read/grep/find/ls/glob, web fetch/search, metadata tools.
- Block: write/edit/execute tools, destructive shell commands.
- Shell allowlist enforced in the middleware.

### UI

- Header indicator: “Plan Mode: ON”
- Plan progress widget: shows steps + completion status.
- Quick command `/todos` to show current plan.

### Storage

- Plan state stored in session metadata (resume‑safe).
- Optional persistence for cross‑session (future phase).

## Integration points

- **UIContext** built inside Textual app and passed to tool execution context.
- **Middleware** for tool gating when Plan Mode is active.
- **Command router** to register `/plan` and `/todos` commands.
- **Extensions API** gains access to UI context and command registration.

## Security and safety

- UI tools must be non‑blocking and cancelable.
- Plan Mode tool gating enforced server‑side (not just UI).
- Commands are namespaced to avoid collisions.

## Milestones

1. UI plugin surface in CLI (minimal API + typed results)
2. Questionnaire extension port (feature parity with Pi basic flows)
3. Plan Mode toggle + tool gating middleware
4. Plan progress UI widget + `/todos` command

## Open questions

- Should UI plugins be allowed in headless mode (fallback to CLI prompt)?
- Should Plan Mode be per‑agent or global per session?
- Do we allow extensions to register commands directly, or via an explicit API?
