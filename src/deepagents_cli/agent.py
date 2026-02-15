"""Agent management and creation for the CLI."""

import os
import shutil
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.sandbox import SandboxBackendProtocol
from deepagents.backends.store import StoreBackend
from deepagents.middleware import MemoryMiddleware, SkillsMiddleware
from langchain.agents.middleware import (
    InterruptOnConfig,
)
from langchain.agents.middleware.types import AgentState
from langchain.messages import ToolCall
from langchain.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.pregel import Pregel
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
import yaml

from deepagents_cli.background_tasks import (
    BACKGROUND_TASKS_PROMPT,
    BackgroundTaskManager,
    BackgroundTaskMiddleware,
)
from deepagents_cli.config import COLORS, config, console, get_default_coding_instructions, settings
from deepagents_cli.extensions import load_extensions
from deepagents_cli.integrations.sandbox_factory import get_default_working_dir
from deepagents_cli.local_context import LocalContextMiddleware
from deepagents_cli.shell import ShellMiddleware


@dataclass(frozen=True)
class _StoreRuntime:
    store: BaseStore
    config: dict[str, Any]
    state: None = None


def _build_store_backend(*, store: BaseStore, assistant_id: str) -> StoreBackend:
    runtime = _StoreRuntime(
        store=store,
        config={"metadata": {"assistant_id": assistant_id}},
    )
    return StoreBackend(
        runtime,
        namespace=lambda _ctx: (assistant_id, "memories"),
    )


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    raw = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(raw) or {}
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, content
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, content
    raw = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(raw) or {}
    except Exception:
        data = None
    body = "\n".join(lines[end_idx + 1 :])
    return (data if isinstance(data, dict) else None), body


def _normalize_skill_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
        return [item for item in items if item]
    return []


_ASSEMBLE_SUBAGENT_DEFAULTS: dict[str, dict[str, str]] = {
    "scout": {
        "description": "Fast codebase recon that returns compressed context for handoff.",
        "prompt": textwrap.dedent(
            """
            You are a scout. Quickly investigate a codebase and return structured findings that another agent can use without re-reading everything.

            Your output will be passed to an agent who has NOT seen the files you explored.

            Thoroughness (infer from task, default medium):
            - Quick: Targeted lookups, key files only
            - Medium: Follow imports, read critical sections
            - Thorough: Trace all dependencies, check tests/types

            Strategy:
            1. Use code search to locate relevant files
            2. Read key sections (not entire files)
            3. Identify types, interfaces, key functions
            4. Note dependencies between files

            Output format:

            ## Files Retrieved
            List with exact line ranges:
            1. `path/to/file.ts` (lines 10-50) - Description of what's here
            2. `path/to/other.ts` (lines 100-150) - Description
            3. ...

            ## Key Code
            Critical types, interfaces, or functions:

            ```typescript
            interface Example {
              // actual code from the files
            }
            ```

            ```typescript
            function keyFunction() {
              // actual implementation
            }
            ```

            ## Architecture
            Brief explanation of how the pieces connect.

            ## Start Here
            Which file to look at first and why.
            """
        ).strip(),
    },
    "planner": {
        "description": "Creates implementation plans from context and requirements.",
        "prompt": textwrap.dedent(
            """
            You are a planning specialist. You receive context (from a scout) and requirements, then produce a clear implementation plan.

            You must NOT make any changes. Only read, analyze, and plan.

            Input format you'll receive:
            - Context/findings from a scout agent
            - Original query or requirements

            Output format:

            ## Goal
            One sentence summary of what needs to be done.

            ## Plan
            Numbered steps, each small and actionable:
            1. Step one - specific file/function to modify
            2. Step two - what to add/change
            3. ...

            ## Files to Modify
            - `path/to/file.ts` - what changes
            - `path/to/other.ts` - what changes

            ## New Files (if any)
            - `path/to/new.ts` - purpose

            ## Risks
            Anything to watch out for.

            Keep the plan concrete. The worker agent will execute it verbatim.
            """
        ).strip(),
    },
    "worker": {
        "description": "General-purpose subagent with full capabilities, isolated context.",
        "prompt": textwrap.dedent(
            """
            You are a worker agent with full capabilities. You operate in an isolated context window to handle delegated tasks without polluting the main conversation.

            Work autonomously to complete the assigned task. Use all available tools as needed.

            Output format when finished:

            ## Completed
            What was done.

            ## Files Changed
            - `path/to/file.ts` - what changed

            ## Notes (if any)
            Anything the main agent should know.

            If handing off to another agent (e.g. reviewer), include:
            - Exact file paths changed
            - Key functions/types touched (short list)
            """
        ).strip(),
    },
    "reviewer": {
        "description": "Code review specialist for quality and security analysis.",
        "prompt": textwrap.dedent(
            """
            You are a senior code reviewer. Analyze code for quality, security, and maintainability.

            Bash is for read-only commands only: `git diff`, `git log`, `git show`. Do NOT modify files or run builds.
            Assume tool permissions are not perfectly enforceable; keep all bash usage strictly read-only.

            Strategy:
            1. Run `git diff` to see recent changes (if applicable)
            2. Read the modified files
            3. Check for bugs, security issues, code smells

            Output format:

            ## Files Reviewed
            - `path/to/file.ts` (lines X-Y)

            ## Critical (must fix)
            - `file.ts:42` - Issue description

            ## Warnings (should fix)
            - `file.ts:100` - Issue description

            ## Suggestions (consider)
            - `file.ts:150` - Improvement idea

            ## Summary
            Overall assessment in 2-3 sentences.

            Be specific with file paths and line numbers.
            """
        ).strip(),
    },
}


def _candidate_subagent_prompt_paths(
    *,
    assistant_id: str,
    subagent_name: str,
) -> list[Path]:
    paths: list[Path] = []
    project_root = settings.project_root
    if project_root:
        base = project_root / ".deepagents" / "subagents"
        paths.extend(
            [
                base / f"{subagent_name}.md",
                base / subagent_name / "SYSTEM.md",
                base / subagent_name / "system.md",
            ]
        )

    user_base = settings.get_agent_dir(assistant_id) / "subagents"
    paths.extend(
        [
            user_base / f"{subagent_name}.md",
            user_base / subagent_name / "SYSTEM.md",
            user_base / subagent_name / "system.md",
        ]
    )
    return paths


def _load_assemble_subagent_prompt(
    *,
    assistant_id: str,
    subagent_name: str,
) -> tuple[str, str]:
    defaults = _ASSEMBLE_SUBAGENT_DEFAULTS[subagent_name]
    default_prompt = defaults["prompt"]
    default_description = defaults["description"]

    for path in _candidate_subagent_prompt_paths(
        assistant_id=assistant_id,
        subagent_name=subagent_name,
    ):
        if not path.exists():
            continue
        try:
            content = path.read_text()
        except Exception:
            continue

        frontmatter, body = _split_frontmatter(content)
        prompt = body.strip() or content.strip()
        if not prompt:
            continue

        description = default_description
        if frontmatter:
            desc = frontmatter.get("description")
            if isinstance(desc, str) and desc.strip():
                description = desc.strip()

        return prompt, description

    return default_prompt, default_description


def _find_subagent_agents_md(assistant_id: str, subagent_name: str) -> Path | None:
    project_root = settings.project_root
    if project_root:
        project_path = (
            project_root / ".deepagents" / "subagents" / subagent_name / "AGENTS.md"
        )
        if project_path.exists():
            return project_path

    user_path = settings.get_agent_dir(assistant_id) / "subagents" / subagent_name / "AGENTS.md"
    if user_path.exists():
        return user_path

    return None


def _build_subagent_skills_cache(
    *,
    assistant_id: str,
    subagent_name: str,
    skills: list[str],
) -> Path | None:
    if not skills:
        return None

    cache_dir = (
        settings.get_agent_dir(assistant_id)
        / "subagents"
        / subagent_name
        / ".skills_cache"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    for child in cache_dir.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)

    project_skills_dir = settings.get_project_skills_dir()
    user_skills_dir = settings.get_user_skills_dir(assistant_id)

    linked = 0
    for skill_name in skills:
        src = None
        if project_skills_dir:
            candidate = project_skills_dir / skill_name
            if candidate.is_dir():
                src = candidate
        if src is None:
            candidate = user_skills_dir / skill_name
            if candidate.is_dir():
                src = candidate

        if src is None:
            console.print(
                f"[yellow]⚠️ Subagent '{subagent_name}' skill not found: {skill_name}[/yellow]"
            )
            continue

        dest = cache_dir / skill_name
        if dest.exists() or dest.is_symlink():
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        try:
            dest.symlink_to(src, target_is_directory=True)
        except Exception:
            shutil.copytree(src, dest, dirs_exist_ok=True)
        linked += 1

    return cache_dir if linked else None


def _resolve_subagent_skills_sources(
    *,
    assistant_id: str,
    subagent_name: str,
) -> list[str] | None:
    agents_md = _find_subagent_agents_md(assistant_id, subagent_name)
    if not agents_md:
        return None

    frontmatter = _parse_frontmatter(agents_md.read_text())
    if not frontmatter:
        return None

    skill_names = _normalize_skill_list(frontmatter.get("skills"))
    if not skill_names:
        return None

    cache_dir = _build_subagent_skills_cache(
        assistant_id=assistant_id,
        subagent_name=subagent_name,
        skills=skill_names,
    )
    if not cache_dir:
        return None

    return [cache_dir.as_posix()]


def _apply_subagent_skills_from_agents_md(
    *,
    assistant_id: str,
    subagent_spec: dict[str, Any],
) -> dict[str, Any]:
    name = subagent_spec.get("name")
    if not name or subagent_spec.get("skills"):
        return subagent_spec

    resolved = _resolve_subagent_skills_sources(
        assistant_id=assistant_id,
        subagent_name=str(name),
    )
    if not resolved:
        return subagent_spec

    updated = dict(subagent_spec)
    updated["skills"] = resolved
    return updated


def _build_assemble_subagents(*, assistant_id: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in _ASSEMBLE_SUBAGENT_DEFAULTS:
        prompt, description = _load_assemble_subagent_prompt(
            assistant_id=assistant_id,
            subagent_name=name,
        )
        spec = {
            "name": name,
            "description": description,
            "system_prompt": prompt,
        }
        spec = _apply_subagent_skills_from_agents_md(
            assistant_id=assistant_id,
            subagent_spec=spec,
        )
        specs.append(spec)
    return specs


def list_agents() -> None:
    """List all available agents."""
    agents_dir = settings.user_deepagents_dir

    if not agents_dir.exists() or not any(agents_dir.iterdir()):
        console.print("[yellow]No agents found.[/yellow]")
        console.print(
            "[dim]Agents will be created in ~/.deepagents/ when you first use them.[/dim]",
            style=COLORS["dim"],
        )
        return

    console.print("\n[bold]Available Agents:[/bold]\n", style=COLORS["primary"])

    for agent_path in sorted(agents_dir.iterdir()):
        if agent_path.is_dir():
            agent_name = agent_path.name
            agent_md = agent_path / "AGENTS.md"

            if agent_md.exists():
                console.print(f"  • [bold]{agent_name}[/bold]", style=COLORS["primary"])
                console.print(f"    {agent_path}", style=COLORS["dim"])
            else:
                console.print(
                    f"  • [bold]{agent_name}[/bold] [dim](incomplete)[/dim]", style=COLORS["tool"]
                )
                console.print(f"    {agent_path}", style=COLORS["dim"])

    console.print()


def reset_agent(agent_name: str, source_agent: str | None = None) -> None:
    """Reset an agent to default or copy from another agent."""
    agents_dir = settings.user_deepagents_dir
    agent_dir = agents_dir / agent_name

    if source_agent:
        source_dir = agents_dir / source_agent
        source_md = source_dir / "AGENTS.md"

        if not source_md.exists():
            console.print(
                f"[bold red]Error:[/bold red] Source agent '{source_agent}' not found "
                "or has no AGENTS.md"
            )
            return

        source_content = source_md.read_text()
        action_desc = f"contents of agent '{source_agent}'"
    else:
        source_content = get_default_coding_instructions()
        action_desc = "default"

    if agent_dir.exists():
        shutil.rmtree(agent_dir)
        console.print(f"Removed existing agent directory: {agent_dir}", style=COLORS["tool"])

    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agent_dir / "AGENTS.md"
    agent_md.write_text(source_content)

    console.print(f"✓ Agent '{agent_name}' reset to {action_desc}", style=COLORS["primary"])
    console.print(f"Location: {agent_dir}\n", style=COLORS["dim"])


def get_system_prompt(assistant_id: str, sandbox_type: str | None = None) -> str:
    """Get the base system prompt for the agent.

    Args:
        assistant_id: The agent identifier for path references
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona").
                     If None, agent is operating in local mode.

    Returns:
        The system prompt string (without AGENTS.md content)
    """
    agent_dir_path = f"~/.deepagents/{assistant_id}"

    if sandbox_type:
        # Get provider-specific working directory

        working_dir = get_default_working_dir(sandbox_type)

        working_dir_section = f"""### Current Working Directory

You are operating in a **remote Linux sandbox** at `{working_dir}`.

All code execution and file operations happen in this sandbox environment.

**Important:**
- The CLI is running locally on the user's machine, but you execute code remotely
- Use `{working_dir}` as your working directory for all operations

"""
    else:
        cwd = Path.cwd()
        working_dir_section = f"""### Current Working Directory

The filesystem backend is currently operating in: `{cwd}`

### File System and Paths

**IMPORTANT - Path Handling:**
- All file paths must be absolute paths (e.g., `{cwd}/file.txt`)
- Use the working directory to construct absolute paths
- Example: To create a file in your working directory, use `{cwd}/research_project/file.md`
- Never use relative paths - always construct full absolute paths

"""

    memory_store_section = """### Persistent Memory Store

Use `/memories/` for long-term notes that should persist across threads and runs.
Example: `/memories/project_notes.md`

"""

    return (
        working_dir_section
        + memory_store_section
        + f"""### Skills Directory

Your skills are stored at: `{agent_dir_path}/skills/`
Skills may contain scripts or supporting files. When executing skill scripts with bash, use the real filesystem path:
Example: `bash python {agent_dir_path}/skills/web-research/script.py`

### Human-in-the-Loop Tool Approval

Some tool calls require user approval before execution. When a tool call is rejected by the user:
1. Accept their decision immediately - do NOT retry the same command
2. Explain that you understand they rejected the action
3. Suggest an alternative approach or ask for clarification
4. Never attempt the exact same rejected command again

Respect the user's decisions and work with them collaboratively.

### Web Search Tool Usage

When you use the web_search tool:
1. The tool will return search results with titles, URLs, and content excerpts
2. You MUST read and process these results, then respond naturally to the user
3. NEVER show raw JSON or tool results directly to the user
4. Synthesize the information from multiple sources into a coherent answer
5. Cite your sources by mentioning page titles or URLs when relevant
6. If the search doesn't find what you need, explain what you found and ask clarifying questions

The user only sees your text responses - not tool results. Always provide a complete, natural language answer after using web_search.

### Todo List Management

When using the write_todos tool:
1. Keep the todo list MINIMAL - aim for 3-6 items maximum
2. Only create todos for complex, multi-step tasks that truly need tracking
3. Break down work into clear, actionable items without over-fragmenting
4. For simple tasks (1-2 steps), just do them directly without creating todos
5. When first creating a todo list for a task, ALWAYS ask the user if the plan looks good before starting work
   - Create the todos, let them render, then ask: "Does this plan look good?" or similar
   - Wait for the user's response before marking the first todo as in_progress
   - If they want changes, adjust the plan accordingly
6. Update todo status promptly as you complete each item

The todo list is a planning tool - use it judiciously to avoid overwhelming the user with excessive task tracking."""
    )


def _format_write_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format write_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    content = args.get("content", "")

    action = "Overwrite" if Path(file_path).exists() else "Create"
    line_count = len(content.splitlines())

    return f"File: {file_path}\nAction: {action} file\nLines: {line_count}"


def _format_edit_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format edit_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    replace_all = bool(args.get("replace_all", False))

    return (
        f"File: {file_path}\n"
        f"Action: Replace text ({'all occurrences' if replace_all else 'single occurrence'})"
    )


def _format_web_search_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format web_search tool call for approval prompt."""
    args = tool_call["args"]
    query = args.get("query", "unknown")
    max_results = args.get("max_results", 5)

    return f"Query: {query}\nMax results: {max_results}\n\n⚠️  This will use Tavily API credits"


def _format_warp_grep_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format warp_grep tool call for approval prompt."""
    args = tool_call["args"]
    query = args.get("query", "unknown")
    repo_root = args.get("repo_root")
    details = [f"Query: {query}"]
    if repo_root:
        details.append(f"Repo Root: {repo_root}")
    details.append("\n⚠️  This will use Morph API credits")
    return "\n".join(details)


def _format_fetch_url_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format fetch_url tool call for approval prompt."""
    args = tool_call["args"]
    url = args.get("url", "unknown")
    timeout = args.get("timeout", 30)

    return f"URL: {url}\nTimeout: {timeout}s\n\n⚠️  Will fetch and convert web content to markdown"


def _format_fast_apply_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format fast_apply tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    instruction = args.get("instruction", "")
    model = args.get("model", "auto")

    instruction_preview = instruction
    if len(instruction_preview) > 200:
        instruction_preview = instruction_preview[:200] + "..."

    return (
        f"File: {file_path}\n"
        f"Model: {model}\n"
        f"Instruction: {instruction_preview}\n\n"
        "⚠️  This will call Morph Fast Apply and overwrite the file"
    )


def _format_task_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format task (subagent) tool call for approval prompt.

    The task tool signature is: task(description: str, subagent_type: str)
    The description contains all instructions that will be sent to the subagent.
    """
    args = tool_call["args"]
    description = args.get("description", "unknown")
    subagent_type = args.get("subagent_type", "unknown")

    # Truncate description if too long for display
    description_preview = description
    if len(description) > 500:
        description_preview = description[:500] + "..."

    return (
        f"Subagent Type: {subagent_type}\n\n"
        f"Task Instructions:\n"
        f"{'─' * 40}\n"
        f"{description_preview}\n"
        f"{'─' * 40}\n\n"
        f"⚠️  Subagent will have access to file operations and shell commands"
    )


def _format_shell_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format shell tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Shell Command: {command}\nWorking Directory: {Path.cwd()}"


def _format_execute_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format execute tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Execute Command: {command}\nLocation: Remote Sandbox"


def _add_interrupt_on() -> dict[str, InterruptOnConfig]:
    """Configure human-in-the-loop interrupt_on settings for destructive tools."""
    shell_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_shell_description,
    }

    execute_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_execute_description,
    }

    write_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_write_file_description,
    }

    edit_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_edit_file_description,
    }

    web_search_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_web_search_description,
    }

    fetch_url_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_fetch_url_description,
    }

    warp_grep_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_warp_grep_description,
    }

    fast_apply_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_fast_apply_description,
    }

    task_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_task_description,
    }
    return {
        "shell": shell_interrupt_config,
        "execute": execute_interrupt_config,
        "write_file": write_file_interrupt_config,
        "edit_file": edit_file_interrupt_config,
        "web_search": web_search_interrupt_config,
        "fetch_url": fetch_url_interrupt_config,
        "warp_grep": warp_grep_interrupt_config,
        "fast_apply": fast_apply_interrupt_config,
        "task": task_interrupt_config,
    }


def create_cli_agent(
    model: str | BaseChatModel,
    assistant_id: str,
    *,
    tools: list[BaseTool] | None = None,
    sandbox: SandboxBackendProtocol | None = None,
    sandbox_type: str | None = None,
    system_prompt: str | None = None,
    auto_approve: bool = False,
    enable_memory: bool = True,
    enable_skills: bool = True,
    enable_shell: bool = True,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    extensions: list[str] | None = None,
    extensions_only: bool = False,
    extensions_disabled: bool = False,
) -> tuple[Pregel, CompositeBackend, BackgroundTaskManager]:
    """Create a CLI-configured agent with flexible options.

    This is the main entry point for creating a deepagents CLI agent, usable both
    internally and from external code (e.g., benchmarking frameworks, Harbor).

    Args:
        model: LLM model to use (e.g., "provider:model-id")
        assistant_id: Agent identifier for memory/state storage
        tools: Additional tools to provide to agent
        sandbox: Optional sandbox backend for remote execution (e.g., ModalBackend).
                 If None, uses local filesystem + shell.
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona").
                     Used for system prompt generation.
        system_prompt: Override the default system prompt. If None, generates one
                      based on sandbox_type and assistant_id.
        auto_approve: If True, automatically approves all tool calls without human
                     confirmation. Useful for automated workflows.
        enable_memory: Enable MemoryMiddleware for persistent memory
        enable_skills: Enable SkillsMiddleware for custom agent skills
        enable_shell: Enable ShellMiddleware for local shell execution (only in local mode)
        checkpointer: Optional checkpointer for session persistence. If None, uses
                     InMemorySaver (no persistence across CLI invocations).
        extensions: Explicit extensions to load (paths or module:func strings)
        extensions_only: If True, skip auto-discovered extensions
        extensions_disabled: If True, disable all extensions

    Returns:
        3-tuple of (agent_graph, backend, task_manager)
        - agent_graph: Configured LangGraph Pregel instance ready for execution
        - composite_backend: CompositeBackend for file operations
        - task_manager: BackgroundTaskManager for tracking background sub-agent tasks
    """
    tools = tools or []

    # Setup agent directory for persistent memory (if enabled)
    if enable_memory or enable_skills:
        agent_dir = settings.ensure_agent_dir(assistant_id)
        agent_md = agent_dir / "AGENTS.md"
        if not agent_md.exists():
            source_content = get_default_coding_instructions()
            agent_md.write_text(source_content)

    # Skills directories (if enabled)
    skills_dir = None
    project_skills_dir = None
    if enable_skills:
        skills_dir = settings.ensure_user_skills_dir(assistant_id)
        project_skills_dir = settings.get_project_skills_dir()

    # Build middleware stack based on enabled features
    agent_middleware = []

    # Add memory middleware
    if enable_memory:
        memory_sources = [str(settings.get_user_agent_md_path(assistant_id))]
        project_agent_md = settings.get_project_agent_md_path()
        if project_agent_md:
            memory_sources.append(str(project_agent_md))

        agent_middleware.append(
            MemoryMiddleware(
                backend=FilesystemBackend(),
                sources=memory_sources,
            )
        )

    # Add skills middleware
    if enable_skills:
        sources = [str(skills_dir)]
        if project_skills_dir:
            sources.append(str(project_skills_dir))

        agent_middleware.append(
            SkillsMiddleware(
                backend=FilesystemBackend(),
                sources=sources,
            )
        )

    # CONDITIONAL SETUP: Local vs Remote Sandbox
    if sandbox is None:
        # ========== LOCAL MODE ==========
        backend = FilesystemBackend()

        # Local context middleware (git info, directory tree, etc.)
        agent_middleware.append(LocalContextMiddleware())

        # Add shell middleware (only in local mode)
        if enable_shell:
            # Create environment for shell commands
            # Restore user's original LANGSMITH_PROJECT so their code traces separately
            shell_env = os.environ.copy()
            if settings.user_langchain_project:
                shell_env["LANGSMITH_PROJECT"] = settings.user_langchain_project

            agent_middleware.append(
                ShellMiddleware(
                    workspace_root=str(Path.cwd()),
                    env=shell_env,
                )
            )
    else:
        # ========== REMOTE SANDBOX MODE ==========
        backend = sandbox  # Remote sandbox (ModalBackend, etc.)
        # Note: Shell middleware not used in sandbox mode
        # File operations and execute tool are provided by the sandbox backend

    # Get or use custom system prompt
    if system_prompt is None:
        system_prompt = get_system_prompt(assistant_id=assistant_id, sandbox_type=sandbox_type)

    # Configure interrupt_on based on auto_approve setting
    if auto_approve:
        # No interrupts - all tools run automatically
        interrupt_on = {}
    else:
        # Full HITL for destructive operations
        interrupt_on = _add_interrupt_on()

    # Set up composite backend with routing
    # For local FilesystemBackend, route large tool results to /tmp to avoid polluting
    # the working directory. For sandbox backends, no special routing is needed.
    if sandbox is None:
        # Local mode: Route large results to a unique temp directory
        large_results_dir = tempfile.mkdtemp(prefix="deepagents_large_results_")
        large_results_backend = FilesystemBackend(
            root_dir=large_results_dir,
            virtual_mode=True,
        )
        routes: dict[str, Any] = {
            "/large_tool_results/": large_results_backend,
        }
        if store is not None:
            routes["/memories/"] = _build_store_backend(
                store=store,
                assistant_id=assistant_id,
            )
        composite_backend = CompositeBackend(
            default=backend,
            routes=routes,
        )
    else:
        # Sandbox mode: No special routing needed
        routes: dict[str, Any] = {}
        if store is not None:
            routes["/memories/"] = _build_store_backend(
                store=store,
                assistant_id=assistant_id,
            )
        composite_backend = CompositeBackend(
            default=backend,
            routes=routes,
        )

    # Load extensions once backend routing is configured
    extension_manager = load_extensions(
        assistant_id=assistant_id,
        project_root=settings.project_root,
        store=store,
        backend=composite_backend,
        explicit=extensions or [],
        only_explicit=extensions_only,
        disabled=extensions_disabled,
    )

    if extension_manager.prompt_additions:
        prompt_additions = "\n\n".join(extension_manager.prompt_additions)
        if system_prompt.endswith("\n"):
            system_prompt = f"{system_prompt}\n{prompt_additions}"
        else:
            system_prompt = f"{system_prompt}\n\n{prompt_additions}"

    if extension_manager.tools:
        tools.extend(extension_manager.tools)

    if extension_manager.middleware:
        agent_middleware.extend(extension_manager.middleware)

    if extension_manager.has_hooks():
        agent_middleware.append(extension_manager.build_middleware())

    available_tool_names: set[str] = set()
    for tool in tools:
        tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if isinstance(tool_name, str) and tool_name:
            available_tool_names.add(tool_name)
    setattr(composite_backend, "available_tool_names", available_tool_names)

    # Create the agent
    # Use provided checkpointer or fallback to InMemorySaver
    final_checkpointer = checkpointer if checkpointer is not None else InMemorySaver()

    tool_by_name = {
        getattr(tool, "__name__", None): tool
        for tool in tools
        if getattr(tool, "__name__", None)
    }

    # Optional specialized subagents (warp_grep / fast_apply)
    subagents: list[dict[str, Any]] = []
    warp_grep_tool = tool_by_name.get("warp_grep")
    if warp_grep_tool is not None:
        subagent_spec = {
            "name": "code-search",
            "description": "Deep codebase search using Morph WarpGrep.",
            "system_prompt": (
                "You are a code-search specialist. Use the warp_grep tool to find relevant code. "
                "Return concise findings with file paths and line references."
            ),
            "tools": [warp_grep_tool],
        }
        subagent_skills = _resolve_subagent_skills_sources(
            assistant_id=assistant_id,
            subagent_name="code-search",
        )
        if subagent_skills:
            subagent_spec["skills"] = subagent_skills
        subagents.append(subagent_spec)

    fast_apply_tool = tool_by_name.get("fast_apply")
    if fast_apply_tool is not None:
        subagent_spec = {
            "name": "fast-apply",
            "description": "Apply edits quickly using Morph Fast Apply.",
            "system_prompt": (
                "You are an edit application specialist. Use fast_apply to merge code edits. "
                "Confirm file paths and summarize what changed."
            ),
            "tools": [fast_apply_tool],
        }
        subagent_skills = _resolve_subagent_skills_sources(
            assistant_id=assistant_id,
            subagent_name="fast-apply",
        )
        if subagent_skills:
            subagent_spec["skills"] = subagent_skills
        subagents.append(subagent_spec)

    assemble_subagents = _build_assemble_subagents(assistant_id=assistant_id)
    if assemble_subagents:
        existing = {
            spec.get("name")
            for spec in subagents
            if isinstance(spec, dict) and spec.get("name")
        }
        for subagent_spec in assemble_subagents:
            if subagent_spec.get("name") in existing:
                continue
            subagents.append(subagent_spec)

    if extension_manager.subagents:
        for subagent_spec in extension_manager.subagents:
            if not isinstance(subagent_spec, dict):
                console.print(
                    "[yellow]⚠️ Extension subagent ignored (invalid spec type).[/yellow]"
                )
                continue
            if not subagent_spec.get("name"):
                console.print(
                    "[yellow]⚠️ Extension subagent missing name; skipped.[/yellow]"
                )
                continue
            subagents.append(
                _apply_subagent_skills_from_agents_md(
                    assistant_id=assistant_id,
                    subagent_spec=subagent_spec,
                )
            )

    # Background task middleware for non-blocking sub-agent execution
    task_manager = BackgroundTaskManager()
    bg_middleware = BackgroundTaskMiddleware(task_manager)
    agent_middleware.append(bg_middleware)

    # Inject background task instructions into system prompt
    if system_prompt:
        system_prompt += BACKGROUND_TASKS_PROMPT

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        subagents=subagents if subagents else None,
        backend=composite_backend,
        store=store,
        middleware=agent_middleware,
        interrupt_on=interrupt_on,
        checkpointer=final_checkpointer,
    ).with_config(config)
    setattr(agent, "available_tool_names", available_tool_names)
    return agent, composite_backend, task_manager
