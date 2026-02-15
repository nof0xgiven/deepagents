"""Background task execution for non-blocking sub-agent launches."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class BackgroundTaskManager:
    """Manages background asyncio tasks for sub-agent execution.

    Launches sub-agent tool calls as background tasks, tracks their status,
    and provides check/wait/cancel operations.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._start_times: dict[str, float] = {}
        self._types: dict[str, str] = {}
        self._descriptions: dict[str, str] = {}
        self._counter: dict[str, int] = {}
        self._on_complete_callbacks: list[Callable[[str, dict], Any]] = []
        self._on_launch_callbacks: list[Callable[[str], Any]] = []

    def generate_id(self, subagent_type: str) -> str:
        """Generate a unique task ID based on subagent type."""
        count = self._counter.get(subagent_type, 0) + 1
        self._counter[subagent_type] = count
        return f"{subagent_type}-{count}"

    def launch(
        self,
        task_id: str,
        handler: Callable[..., Awaitable],
        request: Any,
        description: str = "",
    ) -> None:
        """Launch a background task wrapping the original tool handler.

        Args:
            task_id: Unique identifier for this task.
            handler: The original awrap_tool_call handler to invoke.
            request: The ToolCallRequest to pass to the handler.
            description: Human-readable description of what the task does.
        """
        self._start_times[task_id] = time.monotonic()
        self._descriptions[task_id] = description
        task = asyncio.create_task(self._run_task(task_id, handler, request))
        self._tasks[task_id] = task

        for callback in self._on_launch_callbacks:
            try:
                callback(task_id)
            except Exception:
                pass

    async def _run_task(
        self,
        task_id: str,
        handler: Callable[..., Awaitable],
        request: Any,
    ) -> None:
        """Execute the handler and store the result."""
        try:
            result = await handler(request)
            # Extract content from ToolMessage or Command
            if isinstance(result, ToolMessage):
                content = result.content
            elif hasattr(result, "update") and isinstance(result.update, dict):
                # Command object - extract relevant content
                messages = result.update.get("messages", [])
                if messages:
                    last = messages[-1]
                    content = last.content if hasattr(last, "content") else str(last)
                else:
                    content = str(result)
            else:
                content = str(result)

            elapsed = time.monotonic() - self._start_times[task_id]
            self._results[task_id] = {
                "status": "completed",
                "content": content,
                "duration": round(elapsed, 1),
            }
        except asyncio.CancelledError:
            self._results[task_id] = {
                "status": "cancelled",
                "error": "Task was cancelled.",
            }
            return
        except Exception as exc:
            elapsed = time.monotonic() - self._start_times[task_id]
            error_msg = str(exc)
            # Handle sub-agent HITL interrupts gracefully
            if "GraphInterrupt" in type(exc).__name__ or "interrupt" in error_msg.lower():
                error_msg = (
                    "Sub-agent requires approval — "
                    "try running this task with wait_for_task instead."
                )
            self._results[task_id] = {
                "status": "failed",
                "error": error_msg,
                "duration": round(elapsed, 1),
            }

        # Fire completion callbacks
        result_info = self._results[task_id]
        for callback in self._on_complete_callbacks:
            try:
                ret = callback(task_id, result_info)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception:
                pass

    def check(self, task_id: str) -> dict[str, Any]:
        """Non-blocking check of a task's status and result.

        Returns:
            Dict with 'status' ('running'/'completed'/'failed'/'cancelled'/'unknown'),
            plus 'content'/'error'/'elapsed'/'duration' as appropriate.
        """
        if task_id not in self._tasks and task_id not in self._results:
            return {"status": "unknown", "error": f"No task with id '{task_id}'."}

        if task_id in self._results:
            return self._results[task_id]

        # Still running
        elapsed = time.monotonic() - self._start_times.get(task_id, time.monotonic())
        return {"status": "running", "elapsed": round(elapsed, 1)}

    async def wait(self, task_id: str) -> dict[str, Any]:
        """Block until a task completes, then return the result."""
        if task_id in self._results:
            return self._results[task_id]

        task = self._tasks.get(task_id)
        if task is None:
            return {"status": "unknown", "error": f"No task with id '{task_id}'."}

        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

        return self._results.get(task_id, {"status": "unknown", "error": "No result stored."})

    def list_tasks(self) -> list[dict[str, Any]]:
        """List all tracked tasks with their status."""
        tasks = []
        all_ids = set(self._tasks.keys()) | set(self._results.keys())
        for task_id in sorted(all_ids):
            info = self.check(task_id)
            info["task_id"] = task_id
            info["type"] = self._types.get(task_id, "unknown")
            info["description"] = self._descriptions.get(task_id, "")
            tasks.append(info)
        return tasks

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task. Returns True if cancelled."""
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def on_launch(self, callback: Callable[[str], Any]) -> None:
        """Register a callback fired when a task is launched.

        Callback signature: (task_id: str) -> None
        """
        self._on_launch_callbacks.append(callback)

    def on_complete(self, callback: Callable[[str, dict], Any]) -> None:
        """Register a callback fired when any task completes.

        Callback signature: (task_id: str, result: dict) -> None
        """
        self._on_complete_callbacks.append(callback)

    @property
    def running_count(self) -> int:
        """Number of currently running tasks."""
        return sum(1 for t in self._tasks.values() if not t.done())

    def cleanup(self) -> None:
        """Cancel all running tasks."""
        for _task_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()


def _make_companion_tools(
    manager: BackgroundTaskManager,
) -> list:
    """Create the companion tools for checking/waiting on background tasks."""

    @tool
    def check_task(task_id: str) -> str:
        """Non-blocking check of a background task's status and result.

        Use this to poll a previously launched background task.
        Returns the current status and result content if completed.

        Args:
            task_id: The task ID returned when the task was launched.
        """
        result = manager.check(task_id)
        status = result["status"]
        if status == "running":
            return f"Task '{task_id}' still running ({result.get('elapsed', '?')}s elapsed)."
        if status == "completed":
            return (
                f"Task '{task_id}' completed ({result.get('duration', '?')}s).\n\n"
                f"Result:\n{result['content']}"
            )
        if status == "failed":
            return f"Task '{task_id}' failed: {result.get('error', 'unknown error')}"
        if status == "cancelled":
            return f"Task '{task_id}' was cancelled."
        return f"Task '{task_id}' not found."

    @tool
    async def wait_for_task(task_id: str) -> str:
        """Block until a background task completes and return its result.

        Use this when you need the result before continuing.
        If the task is already complete, returns immediately.

        Args:
            task_id: The task ID returned when the task was launched.
        """
        result = await manager.wait(task_id)
        status = result["status"]
        if status == "completed":
            return (
                f"Task '{task_id}' completed ({result.get('duration', '?')}s).\n\n"
                f"Result:\n{result['content']}"
            )
        if status == "failed":
            return f"Task '{task_id}' failed: {result.get('error', 'unknown error')}"
        if status == "cancelled":
            return f"Task '{task_id}' was cancelled."
        return f"Task '{task_id}': unexpected status '{status}'."

    @tool
    def list_background_tasks() -> str:
        """List all background tasks with their current status.

        Returns a formatted table of all tracked background tasks.
        """
        tasks = manager.list_tasks()
        if not tasks:
            return "No background tasks."
        lines = ["task_id | type | status | time"]
        lines.append("--- | --- | --- | ---")
        for t in tasks:
            elapsed = t.get("duration", t.get("elapsed", "?"))
            lines.append(f"{t['task_id']} | {t['type']} | {t['status']} | {elapsed}s")
        return "\n".join(lines)

    return [check_task, wait_for_task, list_background_tasks]


# System prompt fragment injected into the main agent prompt
BACKGROUND_TASKS_PROMPT = """\

## Background Task Execution
When you use the `task` tool to launch a sub-agent, it runs in the background:
- The tool returns immediately with a task ID (e.g., "general-purpose-1")
- You can continue talking to the user or using other tools
- Use `check_task(task_id)` to poll status without blocking
- Use `wait_for_task(task_id)` if you need the result before continuing
- Use `list_background_tasks()` to see all active/completed tasks

Choose your approach based on need:
- Fire multiple scouts in parallel, then check_task each one later
- Launch a worker, continue discussing with user, wait_for_task when ready
- Launch and immediately wait_for_task when you need the result right now"""


class BackgroundTaskMiddleware(AgentMiddleware):
    """Middleware that intercepts `task` tool calls and runs them in the background.

    Instead of blocking the LLM while a sub-agent executes, this middleware:
    1. Intercepts all `task` tool calls via awrap_tool_call
    2. Spawns the sub-agent as a background asyncio.Task
    3. Returns an immediate ToolMessage with a task ID
    4. The LLM regains control instantly and can choose to:
       - Continue talking (non-blocking)
       - Call check_task(task_id) to poll
       - Call wait_for_task(task_id) to block until done
    """

    def __init__(self, task_manager: BackgroundTaskManager) -> None:
        self.task_manager = task_manager
        self.tools = _make_companion_tools(task_manager)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Intercept task tool calls and launch them in the background."""
        tool_call = request.tool_call
        if tool_call["name"] != "task":
            return await handler(request)

        args = tool_call.get("args", {})
        subagent_type = args.get("subagent_type", "unknown")
        description = args.get("description", "")
        task_id = self.task_manager.generate_id(subagent_type)

        # Track the subagent type
        self.task_manager._types[task_id] = subagent_type

        # Launch in background
        self.task_manager.launch(task_id, handler, request, description=description)

        return ToolMessage(
            content=(
                f"Background task '{task_id}' launched ({subagent_type}).\n"
                f"Working on: {description[:120]}\n\n"
                f"Use check_task(task_id='{task_id}') to poll, or "
                f"wait_for_task(task_id='{task_id}') to block until complete."
            ),
            tool_call_id=tool_call["id"],
            name="task",
        )
