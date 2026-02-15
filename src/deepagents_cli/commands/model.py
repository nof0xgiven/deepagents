"""Model and debug slash-command handlers."""

from __future__ import annotations

from deepagents_cli.commands.types import CommandContext, CommandOutcome, HANDLED, NOT_HANDLED
from deepagents_cli.model_registry import resolve_model_query, search_models


def matches_model_or_debug_command(command_lower: str) -> bool:
    """Match `/model*` and `/debug*` commands."""
    return command_lower.startswith("/model") or command_lower.startswith("/debug")


async def handle_model_or_debug_command(context: CommandContext) -> CommandOutcome:
    """Handle model switching and model debug commands."""
    cmd = context.normalized
    command = context.command

    if cmd.startswith("/model"):
        await context.mount_user(command)
        parts = command.strip().split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""

        if query.lower().startswith("set "):
            target = query[4:].strip()
            if not target:
                await context.mount_system("Usage: /model set <model-name>")
                return HANDLED
            entry = resolve_model_query(target, context.model_controller.build_model_catalog())
            await context.switch_model(target, entry)
            return HANDLED

        if not query:
            await context.open_model_selector()
            return HANDLED

        if query.isdigit():
            candidates = context.model_controller.model_candidates
            if not candidates:
                await context.mount_system("No model list available. Run /model to see options.")
                return HANDLED
            index = int(query) - 1
            if index < 0 or index >= len(candidates):
                await context.mount_system("Invalid selection. Use /model to see options.")
                return HANDLED
            entry = candidates[index]
            await context.switch_model(entry.id, entry)
            return HANDLED

        entries = context.model_controller.build_model_catalog()
        exact = resolve_model_query(query, entries)
        if exact:
            await context.switch_model(exact.id, exact)
            return HANDLED

        suggestions = search_models(query, entries)
        context.model_controller.set_model_candidates(suggestions)
        if not suggestions:
            await context.mount_system(
                "No matching models found. Try /model to list available models."
            )
            return HANDLED

        lines = [
            "Matching models:",
            *[
                context.model_controller.format_model_entry(entry, index=i)
                for i, entry in enumerate(suggestions, start=1)
            ],
            "Use /model <number> to select, /model set <name> to force, or /model <query> to retry.",
        ]
        await context.mount_system("\n".join(lines))
        return HANDLED

    if cmd.startswith("/debug"):
        await context.mount_user(command)
        parts = command.strip().split(maxsplit=1)
        target = parts[1].strip().lower() if len(parts) > 1 else ""
        if target and target not in {"model", "models"}:
            await context.mount_system("Usage: /debug model")
            return HANDLED
        lines = context.model_controller.format_debug_model()
        await context.mount_system("\n".join(lines))
        return HANDLED

    return NOT_HANDLED
