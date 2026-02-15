# Non-Blocking Sub-Agent Execution

## Overview

When the AI launches sub-agents via the `task` tool, the conversation no longer blocks until the sub-agent completes. Instead, the `BackgroundTaskMiddleware` intercepts the tool call, spawns the sub-agent as a background asyncio task, and returns control to the LLM immediately. The AI can then continue talking, launch more tasks, or explicitly wait for results when needed.

This is implemented entirely via the LangChain `AgentMiddleware` extension point — zero changes to the `deepagents` pip package or LangGraph internals.

## How It Works

```
User message → LLM decides to call `task` tool
                    ↓
           HITL approval (if enabled)
                    ↓
       BackgroundTaskMiddleware.awrap_tool_call
                    ↓
       Intercepts `task` tool call
       Spawns background asyncio.Task via BackgroundTaskManager
       Returns immediate ToolMessage: "Background task 'scout-1' launched"
                    ↓
       LLM regains control — can:
         • Continue talking to user
         • Launch more background tasks
         • Call check_task("scout-1") to poll status
         • Call wait_for_task("scout-1") to block until done
         • Call list_background_tasks() to see all tasks
                    ↓
       When background task completes:
         • Result stored in BackgroundTaskManager
         • on_complete callback fires → Textual notification toast
         • AI retrieves result via check_task or wait_for_task
```

## Components

### BackgroundTaskManager

Core class that manages background asyncio tasks. Located in `src/deepagents_cli/background_tasks.py`.

**Methods:**
| Method | Description |
|--------|-------------|
| `generate_id(subagent_type)` | Creates unique task IDs like `"scout-1"`, `"worker-2"` |
| `launch(task_id, handler, request)` | Wraps the tool handler in an `asyncio.Task` and starts it |
| `check(task_id)` | Non-blocking status check: `running`/`completed`/`failed`/`cancelled`/`unknown` |
| `wait(task_id)` | Async — blocks until task completes, returns result |
| `list_tasks()` | Returns all tracked tasks with statuses |
| `cancel(task_id)` | Cancels a running task |
| `on_complete(callback)` | Registers a callback fired when any task finishes |
| `cleanup()` | Cancels all running tasks (used on session end) |

### BackgroundTaskMiddleware

Extends `AgentMiddleware`. Intercepts `task` tool calls and spawns them in the background.

**Key behaviors:**
- Only intercepts tools named `"task"` — all other tools pass through unchanged
- Registers three companion tools via `self.tools` (framework collects these automatically)
- Returns a `ToolMessage` with the task ID and usage instructions

### Companion Tools

These are registered on the middleware and automatically added to the agent's tool set by the framework.

| Tool | Type | Description |
|------|------|-------------|
| `check_task(task_id)` | Sync | Non-blocking poll — returns status and result if complete |
| `wait_for_task(task_id)` | Async | Blocks until task finishes, returns result |
| `list_background_tasks()` | Sync | Lists all tasks with status table |

## Integration Points

### agent.py

`create_cli_agent()` instantiates the manager and middleware:

```python
task_manager = BackgroundTaskManager()
bg_middleware = BackgroundTaskMiddleware(task_manager)
agent_middleware.append(bg_middleware)
```

The system prompt is augmented with instructions telling the AI how to use background tasks. The function returns a 3-tuple: `(agent, backend, task_manager)`.

### app.py

`DeepAgentsApp` accepts the `task_manager` and:
- Registers an `on_complete` callback that shows a Textual notification toast
- Cancels all background tasks on interrupt (Escape/Ctrl+C), quit (Ctrl+D), `/clear`, and model switch

### main.py

Threads `task_manager` through `build_agent()` → `run_textual_app()` → `DeepAgentsApp`.

## Edge Cases

### HITL Approval
The `task` tool's interrupt config fires *before* `awrap_tool_call` (separate middleware layer). The user still approves the launch, then the background middleware takes over. No special handling needed.

### Sub-Agent HITL
Sub-agents running in background cannot surface approval prompts to the user. If a background sub-agent hits a `GraphInterrupt`, it's caught and reported as a failure with the message: *"Sub-agent requires approval — try running this task with wait_for_task instead."*

### Command Return Values
The original `task` tool returns a `Command` with state updates. For v1, `check_task`/`wait_for_task` extract and return just the text content, which is sufficient for most use cases.

### Session Persistence
Background tasks are ephemeral — tied to the current asyncio event loop. They are cancelled on session end and not checkpointed. This is by design for v1.

### Already-Completed Tasks
`wait_for_task` on an already-completed task returns the stored result immediately — no blocking.

### Unknown Task IDs
`check_task` and `wait_for_task` on unknown task IDs return a clear error message.

## AI Usage Patterns

The system prompt instructs the AI to choose its approach based on need:

```
# Fire-and-forget with later check
AI: [calls task tool → launches scout-1]
AI: "I've launched a research task. Let me continue while it works..."
AI: [calls check_task("scout-1")]
AI: "The research is done. Here's what I found: ..."

# Parallel launch
AI: [calls task tool → launches scout-1]
AI: [calls task tool → launches scout-2]
AI: [calls check_task("scout-1")] → still running
AI: [calls wait_for_task("scout-2")] → blocks until done
AI: [calls check_task("scout-1")] → now completed

# Immediate wait (synchronous behavior)
AI: [calls task tool → launches worker-1]
AI: [calls wait_for_task("worker-1")] → blocks until done
AI: "Here are the results: ..."
```

## Files

| File | Role |
|------|------|
| `src/deepagents_cli/background_tasks.py` | BackgroundTaskManager + BackgroundTaskMiddleware + companion tools + prompt |
| `src/deepagents_cli/agent.py` | Instantiation, middleware wiring, prompt injection, return signature |
| `src/deepagents_cli/app.py` | UI callbacks, cleanup on lifecycle events |
| `src/deepagents_cli/main.py` | Threading task_manager through the call chain |
