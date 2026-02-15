"""Command registry and dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from deepagents_cli.commands.assemble import handle_assemble_command, matches_assemble_command
from deepagents_cli.commands.core import handle_core_command, matches_core_command
from deepagents_cli.commands.model import (
    handle_model_or_debug_command,
    matches_model_or_debug_command,
)
from deepagents_cli.commands.types import CommandContext, CommandHandler


@dataclass(frozen=True)
class RegisteredCommand:
    """Matcher + async handler pair."""

    matches: Callable[[str], bool]
    handler: CommandHandler


class CommandRegistry:
    """Ordered slash-command dispatcher."""

    def __init__(self, handlers: list[RegisteredCommand]) -> None:
        self._handlers = handlers

    async def dispatch(self, context: CommandContext) -> bool:
        """Dispatch the first matching command handler."""
        for registered in self._handlers:
            if not registered.matches(context.normalized):
                continue
            outcome = await registered.handler(context)
            if outcome.handled:
                return True
        return False


def build_default_registry() -> CommandRegistry:
    """Build the default command registry."""
    return CommandRegistry(
        handlers=[
            RegisteredCommand(matches=matches_core_command, handler=handle_core_command),
            RegisteredCommand(matches=matches_assemble_command, handler=handle_assemble_command),
            RegisteredCommand(
                matches=matches_model_or_debug_command,
                handler=handle_model_or_debug_command,
            ),
        ]
    )
