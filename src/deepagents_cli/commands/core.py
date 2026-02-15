"""Core slash commands."""

from __future__ import annotations

from deepagents_cli.commands.types import CommandContext, CommandOutcome, HANDLED, NOT_HANDLED

# Prompt for /remember command - triggers agent to review conversation and update memory/skills
REMEMBER_PROMPT = """Review our conversation and capture valuable knowledge. Focus especially on **best practices** we discussed or discovered—these are the most important things to preserve.

## Step 1: Identify Best Practices and Key Learnings

Scan the conversation for:

### Best Practices (highest priority)
- **Patterns that worked well** - approaches, techniques, or solutions we found effective
- **Anti-patterns to avoid** - mistakes, gotchas, or approaches that caused problems
- **Quality standards** - criteria we established for good code, documentation, or processes
- **Decision rationale** - why we chose one approach over another

### Other Valuable Knowledge
- Coding conventions and style preferences
- Project architecture decisions
- Workflows and processes we developed
- Tools, libraries, or techniques worth remembering
- Feedback I gave about your behavior or outputs

## Step 2: Decide Where to Store Each Learning

For each best practice or learning, choose the right destination:

### → Memory (AGENTS.md) for preferences and guidelines
Use memory when the knowledge is:
- A preference or guideline (not a multi-step process)
- Something to always keep in mind
- A simple rule or pattern

**Global** (`~/.deepagents/agent/AGENTS.md`): Universal preferences across all projects
**Project** (`.deepagents/AGENTS.md`): Project-specific conventions and decisions

### → Skill for reusable workflows and methodologies
**Create a skill when** we developed:
- A multi-step process worth reusing
- A methodology for a specific type of task
- A workflow with best practices baked in
- A procedure that should be followed consistently

Skills are more powerful than memory entries because they can encode **how** to do something well, not just **what** to remember.

## Step 3: Create Skills for Significant Best Practices

If we established best practices around a workflow or process, capture them in a skill.

**Example:** If we discussed best practices for code review, create a `code-review` skill that encodes those practices into a reusable workflow.

### Skill Location
`~/.deepagents/agent/skills/<skill-name>/SKILL.md`

### Skill Structure
```
skill-name/
├── SKILL.md          (required - main instructions with best practices)
├── scripts/          (optional - executable code)
├── references/       (optional - detailed documentation)
└── assets/           (optional - templates, examples)
```

### SKILL.md Format
```markdown
---
name: skill-name
description: "What this skill does AND when to use it. Include triggers like 'when the user asks to X' or 'when working with Y'. This description determines when the skill activates."
---

# Skill Name

## Overview
Brief explanation of what this skill accomplishes.

## Best Practices
Capture the key best practices upfront:
- Best practice 1: explanation
- Best practice 2: explanation

## Process
Step-by-step instructions (imperative form):
1. First, do X
2. Then, do Y
3. Finally, do Z

## Common Pitfalls
- Pitfall to avoid and why
- Another anti-pattern we discovered
```

### Key Principles
1. **Encode best practices prominently** - Put them near the top so they guide the entire workflow
2. **Concise is key** - Only include non-obvious knowledge. Every paragraph should justify its token cost.
3. **Clear triggers** - The description determines when the skill activates. Be specific.
4. **Imperative form** - Write as commands: "Create a file" not "You should create a file"
5. **Include anti-patterns** - What NOT to do is often as valuable as what to do

## Step 4: Update Memory for Simpler Learnings

For preferences, guidelines, and simple rules that don't warrant a full skill:

```markdown
## Best Practices
- When doing X, always Y because Z
- Avoid A because it leads to B
```

Use `edit_file` to update existing files or `write_file` to create new ones.

## Step 5: Summarize Changes

List what you captured and where you stored it:
- Skills created (with key best practices encoded)
- Memory entries added (with location)
"""


def matches_core_command(command_lower: str) -> bool:
    """Match commands handled by the core command module."""
    if command_lower in {"/quit", "/exit", "/q", "/help", "/version", "/clear", "/threads", "/tokens"}:
        return True
    return command_lower == "/remember" or command_lower.startswith("/remember ")


async def handle_core_command(context: CommandContext) -> CommandOutcome:
    """Handle core app commands."""
    cmd = context.normalized
    command = context.command

    if cmd in {"/quit", "/exit", "/q"}:
        context.exit_app()
        return HANDLED

    if cmd == "/help":
        await context.mount_user(command)
        await context.mount_system(
            "Commands: /assemble, /model, /debug, /quit, /clear, /remember, /tokens, /threads, /help"
        )
        return HANDLED

    if cmd == "/version":
        await context.mount_user(command)
        try:
            from deepagents_cli._version import __version__

            await context.mount_system(f"deepagents version: {__version__}")
        except Exception:
            await context.mount_system("deepagents version: unknown")
        return HANDLED

    if cmd == "/clear":
        await context.clear_messages()
        context.reset_tokens()
        context.clear_status()
        thread_id = context.reset_thread()
        if thread_id:
            await context.mount_system(f"Started new session: {thread_id}")
        return HANDLED

    if cmd == "/threads":
        await context.mount_user(command)
        thread_id = context.current_thread_id()
        if thread_id:
            await context.mount_system(f"Current session: {thread_id}")
        else:
            await context.mount_system("No active session")
        return HANDLED

    if cmd == "/tokens":
        await context.mount_user(command)
        count = context.current_context_tokens()
        if count > 0:
            formatted = f"{count / 1000:.1f}K" if count >= 1000 else str(count)
            await context.mount_system(f"Current context: {formatted} tokens")
        else:
            await context.mount_system("No token usage yet")
        return HANDLED

    if cmd == "/remember" or cmd.startswith("/remember "):
        additional_context = ""
        if cmd.startswith("/remember "):
            additional_context = command.strip()[len("/remember ") :].strip()

        final_prompt = (
            f"{REMEMBER_PROMPT}\n\n**Additional context from user:** {additional_context}"
            if additional_context
            else REMEMBER_PROMPT
        )
        await context.handle_user_message(final_prompt)
        return HANDLED

    return NOT_HANDLED
