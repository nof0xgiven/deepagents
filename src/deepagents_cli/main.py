"""Main entry point and CLI loop for deepagents."""
# ruff: noqa: E402, BLE001, PLR0912, PLR0915

# Suppress deprecation warnings from langchain_core (e.g., Pydantic V1 on Python 3.14+)
# ruff: noqa: E402
import warnings

warnings.filterwarnings("ignore", module="langchain_core._api.deprecation")

import argparse
import asyncio
import contextlib
import os
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Suppress Pydantic v1 compatibility warnings from langchain on Python 3.14+
warnings.filterwarnings("ignore", message=".*Pydantic V1.*", category=UserWarning)

from rich.text import Text

from deepagents_cli._version import __version__

# Now safe to import agent (which imports LangChain modules)
from deepagents_cli.agent import create_cli_agent, list_agents, reset_agent

# CRITICAL: Import config FIRST to set LANGSMITH_PROJECT before LangChain loads
from deepagents_cli.config import (
    ModelConfigurationError,
    NoModelSelectedError,
    console,
    create_model,
    settings,
)
from deepagents_cli.integrations.sandbox_factory import create_sandbox
from deepagents_cli.mcp import open_mcp_tools
from deepagents_cli.sessions import (
    ThreadLockError,
    acquire_thread_lock,
    delete_thread_command,
    generate_thread_id,
    get_checkpointer,
    get_store,
    get_most_recent,
    get_thread_agent,
    list_threads_command,
    thread_exists,
)
from deepagents_cli.skills import execute_skills_command, setup_skills_parser
from deepagents_cli.tools import fast_apply, fetch_url, http_request, warp_grep, web_search
from deepagents_cli.ui import show_help

if TYPE_CHECKING:
    from langgraph.pregel import Pregel


def check_cli_dependencies() -> None:
    """Check if CLI optional dependencies are installed."""
    missing = []

    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")

    try:
        import dotenv  # noqa: F401
    except ImportError:
        missing.append("python-dotenv")

    try:
        import tavily  # noqa: F401
    except ImportError:
        missing.append("tavily-python")

    try:
        import textual  # noqa: F401
    except ImportError:
        missing.append("textual")

    if missing:
        print("\n❌ Missing required CLI dependencies!")
        print("\nThe following packages are required to use the deepagents CLI:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nPlease install them with:")
        print("  pip install deepagents[cli]")
        print("\nOr install all dependencies:")
        print("  pip install 'deepagents[cli]'")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DeepAgents - AI Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"deepagents {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List all available agents")

    # Help command
    subparsers.add_parser("help", help="Show help information")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset an agent")
    reset_parser.add_argument("--agent", required=True, help="Name of agent to reset")
    reset_parser.add_argument(
        "--target", dest="source_agent", help="Copy prompt from another agent"
    )

    # Skills command - setup delegated to skills module
    setup_skills_parser(subparsers)

    # Threads command
    threads_parser = subparsers.add_parser("threads", help="Manage conversation threads")
    threads_sub = threads_parser.add_subparsers(dest="threads_command")

    # threads list
    threads_list = threads_sub.add_parser("list", help="List threads")
    threads_list.add_argument(
        "--agent", default=None, help="Filter by agent name (default: show all)"
    )
    threads_list.add_argument("--limit", type=int, default=20, help="Max threads (default: 20)")

    # threads delete
    threads_delete = threads_sub.add_parser("delete", help="Delete a thread")
    threads_delete.add_argument("thread_id", help="Thread ID to delete")

    # Default interactive mode
    parser.add_argument(
        "--agent",
        default="agent",
        help="Agent identifier for separate memory stores (default: agent).",
    )

    # Thread resume argument - matches PR #638: -r for most recent, -r <ID> for specific
    parser.add_argument(
        "-r",
        "--resume",
        dest="resume_thread",
        nargs="?",
        const="__MOST_RECENT__",
        default=None,
        help="Resume thread: -r for most recent, -r <ID> for specific thread",
    )

    # Initial prompt - auto-submit when session starts
    parser.add_argument(
        "-m",
        "--message",
        dest="initial_prompt",
        help="Initial prompt to auto-submit when session starts",
    )
    parser.add_argument(
        "--no-thread-lock",
        dest="no_thread_lock",
        action="store_true",
        default=False,
        help="Disable exclusive thread locking (allows multiple sessions on the same thread_id).",
    )

    parser.add_argument(
        "--model",
        help="Model alias or provider:model-id. "
        "If omitted, uses model.active from settings.json.",
    )
    parser.add_argument(
        "--reasoning",
        dest="reasoning_effort",
        help="OpenAI reasoning effort (none|low|medium|high|xhigh). "
        "Defaults to DEEPAGENTS_REASONING_EFFORT or 'high'.",
    )
    parser.add_argument(
        "--service-tier",
        dest="service_tier",
        help="OpenAI service tier (default: priority). "
        "Defaults to DEEPAGENTS_SERVICE_TIER or 'priority'.",
    )
    parser.add_argument(
        "--auto-approve",
        dest="auto_approve",
        action="store_true",
        default=True,
        help="Auto-approve tool usage without prompting (disables human-in-the-loop).",
    )
    parser.add_argument(
        "--no-auto-approve",
        dest="auto_approve",
        action="store_false",
        help="Disable auto-approve and require human-in-the-loop confirmations.",
    )
    parser.add_argument(
        "--sandbox",
        choices=["none", "modal", "daytona", "runloop"],
        default="none",
        help="Remote sandbox for code execution (default: none - local only)",
    )
    parser.add_argument(
        "--sandbox-id",
        help="Existing sandbox ID to reuse (skips creation and cleanup)",
    )
    parser.add_argument(
        "--sandbox-setup",
        help="Path to setup script to run in sandbox after creation",
    )
    parser.add_argument(
        "--extensions",
        action="append",
        help="Load extension by path or module:func (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--extensions-only",
        action="store_true",
        help="Only load explicitly listed extensions (skip auto-discovery)",
    )
    parser.add_argument(
        "--no-extensions",
        dest="extensions_disabled",
        action="store_true",
        help="Disable all extensions",
    )
    return parser.parse_args()


def _parse_extension_entries(entries: list[str] | None) -> list[str]:
    if not entries:
        return []
    parsed: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        for part in str(entry).split(","):
            value = part.strip()
            if not value or value in seen:
                continue
            parsed.append(value)
            seen.add(value)
    return parsed


async def run_textual_cli_async(
    assistant_id: str,
    *,
    auto_approve: bool = False,
    sandbox_type: str = "none",
    sandbox_id: str | None = None,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    thread_id: str | None = None,
    is_resumed: bool = False,
    initial_prompt: str | None = None,
    extensions: list[str] | None = None,
    extensions_only: bool = False,
    extensions_disabled: bool = False,
) -> None:
    """Run the Textual CLI interface (async version).

    Args:
        assistant_id: Agent identifier for memory storage
        auto_approve: Whether to auto-approve tool usage
        sandbox_type: Type of sandbox ("none", "modal", "runloop", "daytona")
        sandbox_id: Optional existing sandbox ID to reuse
        model_name: Optional model name to use
        reasoning_effort: Optional OpenAI reasoning effort override
        service_tier: Optional OpenAI service tier override
        thread_id: Thread ID to use (new or resumed)
        is_resumed: Whether this is a resumed session
        initial_prompt: Optional prompt to auto-submit when session starts
        extensions: Explicit extension entries to load
        extensions_only: If True, skip auto-discovered extensions
        extensions_disabled: If True, disable all extensions
    """
    from deepagents_cli.app import run_textual_app

    def build_agent(
        model_name_override: str | None,
        *,
        auto_approve_override: bool,
        reasoning_effort_override: str | None = None,
        service_tier_override: str | None = None,
    ) -> tuple[Pregel, Any, Any]:
        model = create_model(
            model_name_override,
            reasoning_effort=reasoning_effort_override or reasoning_effort,
            service_tier=service_tier_override or service_tier,
        )
        return create_cli_agent(
            model=model,
            assistant_id=assistant_id,
            tools=tools,
            sandbox=sandbox_backend,
            sandbox_type=sandbox_type if sandbox_type != "none" else None,
            auto_approve=auto_approve_override,
            checkpointer=checkpointer,
            store=store,
            extensions=extensions,
            extensions_only=extensions_only,
            extensions_disabled=extensions_disabled,
        )

    # Show thread info
    if is_resumed:
        console.print(f"[#00AEEF]Resuming thread:[/#00AEEF] {thread_id}")
    else:
        console.print(f"[dim]Thread: {thread_id}[/dim]")

    # Use async context manager for checkpointer
    async with get_checkpointer() as checkpointer:
        async with get_store() as store:
            async with open_mcp_tools() as mcp_tools:
                # Create agent with conditional tools
                tools = [http_request, fetch_url, warp_grep, fast_apply]
                if settings.has_tavily:
                    tools.append(web_search)
                if mcp_tools:
                    tools.extend(mcp_tools)

                # Handle sandbox mode
                sandbox_backend = None
                sandbox_cm = None

                if sandbox_type != "none":
                    try:
                        # Create sandbox context manager but keep it open
                        sandbox_cm = create_sandbox(sandbox_type, sandbox_id=sandbox_id)
                        sandbox_backend = sandbox_cm.__enter__()
                    except (ImportError, ValueError, RuntimeError, NotImplementedError) as e:
                        console.print()
                        console.print("[red]❌ Sandbox creation failed[/red]")
                        console.print(Text(str(e), style="dim"))
                        sys.exit(1)

                try:
                    agent = None
                    composite_backend = None
                    task_manager = None
                    try:
                        agent, composite_backend, task_manager = build_agent(
                            model_name,
                            auto_approve_override=auto_approve,
                        )
                    except NoModelSelectedError:
                        agent = None
                        composite_backend = None
                        task_manager = None

                    # Run Textual app
                    await run_textual_app(
                        agent=agent,
                        assistant_id=assistant_id,
                        backend=composite_backend,
                        agent_builder=build_agent,
                        auto_approve=auto_approve,
                        cwd=Path.cwd(),
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                        task_manager=task_manager,
                    )
                except ModelConfigurationError as e:
                    error_text = Text("❌ Failed to configure model: ", style="red")
                    error_text.append(str(e))
                    console.print(error_text)
                    sys.exit(1)
                except Exception as e:
                    error_text = Text("❌ Failed to create agent: ", style="red")
                    error_text.append(str(e))
                    console.print(error_text)
                    sys.exit(1)
                finally:
                    # Clean up sandbox if we created one
                    if sandbox_cm is not None:
                        with contextlib.suppress(Exception):
                            sandbox_cm.__exit__(None, None, None)


def cli_main() -> None:
    """Entry point for console script."""
    # Fix for gRPC fork issue on macOS
    # https://github.com/grpc/grpc/issues/37642
    if sys.platform == "darwin":
        os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

    # Note: LANGSMITH_PROJECT is already overridden in config.py (before LangChain imports)
    # This ensures agent traces → DEEPAGENTS_LANGSMITH_PROJECT
    # Shell commands → user's original LANGSMITH_PROJECT (via ShellMiddleware env)

    # Check dependencies first
    check_cli_dependencies()

    try:
        args = parse_args()
        extensions = _parse_extension_entries(getattr(args, "extensions", None))
        extensions_only = bool(getattr(args, "extensions_only", False))
        extensions_disabled = bool(getattr(args, "extensions_disabled", False))

        if args.command == "help":
            show_help()
        elif args.command == "list":
            list_agents()
        elif args.command == "reset":
            reset_agent(args.agent, args.source_agent)
        elif args.command == "skills":
            execute_skills_command(args)
        elif args.command == "threads":
            if args.threads_command == "list":
                asyncio.run(
                    list_threads_command(
                        agent_name=getattr(args, "agent", None),
                        limit=getattr(args, "limit", 20),
                    )
                )
            elif args.threads_command == "delete":
                asyncio.run(delete_thread_command(args.thread_id))
            else:
                console.print("[yellow]Usage: deepagents threads <list|delete>[/yellow]")
        else:
            # Interactive mode - handle thread resume
            thread_id = None
            is_resumed = False

            if args.resume_thread == "__MOST_RECENT__":
                # -r (no ID): Get most recent thread
                # If --agent specified, filter by that agent; otherwise get most recent overall
                agent_filter = args.agent if args.agent != "agent" else None
                thread_id = asyncio.run(get_most_recent(agent_filter))
                if thread_id:
                    is_resumed = True
                    agent_name = asyncio.run(get_thread_agent(thread_id))
                    if agent_name:
                        args.agent = agent_name
                else:
                    if agent_filter:
                        msg = Text("No previous thread for '", style="yellow")
                        msg.append(args.agent)
                        msg.append("', starting new.", style="yellow")
                    else:
                        msg = Text("No previous threads, starting new.", style="yellow")
                    console.print(msg)

            elif args.resume_thread:
                # -r <ID>: Resume specific thread
                if asyncio.run(thread_exists(args.resume_thread)):
                    thread_id = args.resume_thread
                    is_resumed = True
                    if args.agent == "agent":
                        agent_name = asyncio.run(get_thread_agent(thread_id))
                        if agent_name:
                            args.agent = agent_name
                else:
                    error_msg = Text("Thread '", style="red")
                    error_msg.append(args.resume_thread)
                    error_msg.append("' not found.", style="red")
                    console.print(error_msg)
                    console.print(
                        "[dim]Use 'deepagents threads list' to see available threads.[/dim]"
                    )
                    sys.exit(1)

            # Generate new thread ID if not resuming
            if thread_id is None:
                thread_id = generate_thread_id()

            # Run Textual CLI
            try:
                with acquire_thread_lock(thread_id, enabled=not args.no_thread_lock):
                    asyncio.run(
                        run_textual_cli_async(
                            assistant_id=args.agent,
                            auto_approve=args.auto_approve,
                            sandbox_type=args.sandbox,
                            sandbox_id=args.sandbox_id,
                            model_name=args.model,
                            reasoning_effort=args.reasoning_effort,
                            service_tier=args.service_tier,
                            thread_id=thread_id,
                            is_resumed=is_resumed,
                            initial_prompt=args.initial_prompt,
                            extensions=extensions,
                            extensions_only=extensions_only,
                            extensions_disabled=extensions_disabled,
                        )
                    )
            except ThreadLockError as e:
                console.print(Text(str(e), style="red"))
                sys.exit(1)
    except KeyboardInterrupt:
        # Clean exit on Ctrl+C - suppress ugly traceback
        console.print("\n\n[yellow]Interrupted[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    cli_main()
