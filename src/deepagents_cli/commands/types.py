"""Shared command-dispatch types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from deepagents_cli.model_controller import ModelController
from deepagents_cli.model_registry import ModelEntry

AsyncTextFn = Callable[[str], Awaitable[None]]
AsyncNoArgFn = Callable[[], Awaitable[None]]
SyncNoArgFn = Callable[[], None]
SyncOptStrFn = Callable[[], str | None]
SwitchModelFn = Callable[[str, ModelEntry | None], Awaitable[None]]


@dataclass(frozen=True)
class CommandContext:
    """Execution context passed to slash-command handlers."""

    command: str
    normalized: str
    mount_user: AsyncTextFn
    mount_system: AsyncTextFn
    mount_error: AsyncTextFn
    handle_user_message: AsyncTextFn
    clear_messages: AsyncNoArgFn
    clear_status: SyncNoArgFn
    exit_app: SyncNoArgFn
    reset_tokens: SyncNoArgFn
    reset_thread: SyncOptStrFn
    current_thread_id: SyncOptStrFn
    current_context_tokens: Callable[[], int]
    open_model_selector: AsyncNoArgFn
    switch_model: SwitchModelFn
    model_controller: ModelController
    available_tool_names: Callable[[], set[str]]


@dataclass(frozen=True)
class CommandOutcome:
    """Outcome returned by a command handler."""

    handled: bool


HANDLED = CommandOutcome(handled=True)
NOT_HANDLED = CommandOutcome(handled=False)


class CommandHandler(Protocol):
    """Async slash-command handler interface."""

    async def __call__(self, context: CommandContext) -> CommandOutcome: ...
