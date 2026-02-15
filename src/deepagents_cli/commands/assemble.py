"""`/assemble` slash-command handler."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from deepagents_cli.commands.types import CommandContext, CommandOutcome, HANDLED, NOT_HANDLED
from deepagents_cli.linear_ids import is_linear_identifier


@dataclass(frozen=True)
class AssembleArgs:
    issue_id: str
    include_comments: bool
    max_comments: int
    post_started_comment: bool


def matches_assemble_command(command_lower: str) -> bool:
    """Match `/assemble` commands."""
    return command_lower.startswith("/assemble")


def _parse_assemble_args(command: str) -> AssembleArgs | None:
    tokens = command.strip().split()
    if len(tokens) < 2:
        return None

    issue_id = tokens[1]
    include_comments = True
    max_comments = 20
    post_started_comment = True

    for token in tokens[2:]:
        if token == "--no-comments":
            include_comments = False
        elif token == "--no-comment":
            post_started_comment = False
        elif token.startswith("--max-comments="):
            value = token.split("=", 1)[1].strip()
            if value.isdigit():
                max_comments = int(value)

    return AssembleArgs(
        issue_id=issue_id,
        include_comments=include_comments,
        max_comments=max_comments,
        post_started_comment=post_started_comment,
    )


def _format_comments_section(comments: list[dict[str, object]]) -> str:
    if not comments:
        return "None"
    formatted_comments: list[str] = []
    for comment in comments:
        author = str(comment.get("author") or "unknown")
        created = str(comment.get("createdAt") or "")
        body = str(comment.get("body") or "")
        header = f"**{author}**"
        if created:
            header = f"{header} ({created})"
        formatted_comments.append(f"{header}:\n{body}")
    return "\n\n".join(formatted_comments)


def _comment_instruction_lines(identifier: str, *, can_comment_linear: bool) -> list[str]:
    if can_comment_linear:
        return [
            "Follow this pipeline using the task tool (subagents). After EACH phase completes,",
            f"call `linear_comment` with a concise progress update for ticket `{identifier}`.",
            "",
        ]
    return [
        "Follow this pipeline using the task tool (subagents).",
        "The `linear_comment` tool is unavailable in this session,",
        "so do not attempt ticket comments during execution.",
        "",
    ]


def _build_assemble_prompt(
    *,
    issue: dict[str, object],
    issue_id: str,
    comments: list[dict[str, object]],
    can_comment_linear: bool,
) -> str:
    identifier = str(issue.get("identifier") or issue_id)
    title = str(issue.get("title") or "")
    issue_uuid = str(issue.get("id") or "")
    team = str(issue.get("team") or "")
    state = str(issue.get("state") or "")
    assignee = str(issue.get("assignee") or "")

    prompt_lines = [
        f"Execute this implementation workflow for Linear ticket {identifier}: {title}",
        "",
        "## Ticket Context",
        f"**Identifier:** {identifier}",
        f"**Issue ID:** {issue_uuid or '(unknown)'}",
        f"**Title:** {title}",
        f"**Team:** {team or '(unknown)'}",
        f"**State:** {state or '(unknown)'}",
    ]
    if assignee:
        prompt_lines.append(f"**Assignee:** {assignee}")

    prompt_lines.extend(
        [
            "",
            "### Description",
            str(issue.get("description") or "(No description)"),
            "",
            "### Existing Comments",
            _format_comments_section(comments),
            "",
            "## Instructions",
            *_comment_instruction_lines(identifier, can_comment_linear=can_comment_linear),
            "If a named subagent type is unavailable, fall back to `general-purpose`.",
            "",
            "### Phase 1: Scout and Plan (sequential)",
            '1. Use the task tool with subagent_type "scout" to find all relevant code for',
            f"   {identifier}: {title}. Include file paths and line references in the output.",
            '2. Use the task tool with subagent_type "planner" to produce an implementation plan',
            "   using the scout output. Keep the plan concrete and actionable.",
            "",
            (
                "After both, call `linear_comment` with a summary of findings and the plan."
                if can_comment_linear
                else "After both, capture findings and the plan for the final report."
            ),
            "",
            "### Phase 2: Implement and Review (loop)",
            "Run a worker -> reviewer loop. Repeat up to 3 iterations:",
            "",
            "**Iteration N:**",
            '1. Use the task tool with subagent_type "worker".',
            "   - Iteration 1: pass the full plan from Phase 1 and implement all steps.",
            "   - Iterations 2-3: pass reviewer feedback and fix the issues.",
            (
                "2. After each worker run, call `linear_comment` with what was implemented."
                if can_comment_linear
                else "2. After each worker run, capture what was implemented for the final report."
            ),
            '3. Use the task tool with subagent_type "reviewer" to review the worker output.',
            "   The reviewer should check the plan for completeness and any bugs or gaps.",
            (
                "4. After each reviewer run, call `linear_comment` with the verdict and feedback."
                if can_comment_linear
                else "4. After each reviewer run, capture verdict and feedback for the final report."
            ),
            "5. Stop if the reviewer reports all steps complete; otherwise iterate.",
            "   If iteration 3 finishes with issues, stop and report what remains.",
            "",
            "### Phase 3: Report",
            "Summarize completed steps, files changed, remaining issues, and iterations used.",
            (
                "Post a final `linear_comment` with the summary and status."
                if can_comment_linear
                else "Include complete status and outcomes in the final response output."
            ),
        ]
    )
    return "\n".join(prompt_lines)


async def handle_assemble_command(context: CommandContext) -> CommandOutcome:
    """Handle `/assemble` command execution."""
    if not matches_assemble_command(context.normalized):
        return NOT_HANDLED

    await context.mount_user(context.command)
    tokens = context.command.strip().split()
    if len(tokens) < 2:
        await context.mount_system(
            "Usage: /assemble TEAM-123 [--no-comments] [--max-comments=N] [--no-comment]"
        )
        return HANDLED
    issue_id = tokens[1]
    if not is_linear_identifier(issue_id):
        try:
            uuid.UUID(issue_id)
        except ValueError:
            await context.mount_system("Invalid ticket ID. Use format TEAM-123 or a Linear issue UUID.")
            return HANDLED

    parsed = _parse_assemble_args(context.command)
    if parsed is None:
        await context.mount_error("Assemble failed: could not parse assemble arguments")
        return HANDLED

    try:
        from deepagents_cli.ext import linear as linear_ext

        data = await asyncio.to_thread(
            linear_ext.linear_assemble,
            parsed.issue_id,
            include_comments=parsed.include_comments,
            max_comments=parsed.max_comments,
            post_started_comment=parsed.post_started_comment,
        )
    except Exception as exc:
        await context.mount_error(f"Assemble failed: {exc}")
        return HANDLED

    issue = data.get("issue") if isinstance(data, dict) else None
    comments = data.get("comments") if isinstance(data, dict) else None
    issue_payload = issue if isinstance(issue, dict) else {}
    comments_payload = comments if isinstance(comments, list) else []
    can_comment_linear = "linear_comment" in context.available_tool_names()
    prompt = _build_assemble_prompt(
        issue=issue_payload,
        issue_id=parsed.issue_id,
        comments=comments_payload,
        can_comment_linear=can_comment_linear,
    )
    await context.handle_user_message(prompt)
    return HANDLED
