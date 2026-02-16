"""Textual UI application for deepagents-cli."""
# ruff: noqa: BLE001, PLR0912, PLR2004, S110

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.app import App
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.css.query import NoMatches
from textual.events import Click, MouseUp
from textual.widgets import Static

from deepagents_cli.clipboard import copy_selection_to_clipboard
from deepagents_cli.commands import build_default_registry
from deepagents_cli.commands.types import CommandContext
from deepagents_cli.config import settings
from deepagents_cli.model_registry import ModelEntry
from deepagents_cli.model_controller import ModelController
from deepagents_cli.widgets.model_selector import ModelSelectorScreen
from deepagents_cli.textual_adapter import TextualUIAdapter, execute_task_textual
from deepagents_cli.widgets.approval import ApprovalMenu
from deepagents_cli.widgets.chat_input import ChatInput, SlashCommandMenu
from deepagents_cli.widgets.loading import LoadingWidget
from deepagents_cli.widgets.messages import (
    AssistantMessage,
    ErrorMessage,
    SystemMessage,
    ToolCallMessage,
    UserMessage,
)
from deepagents_cli.widgets.agents_pill import AgentsPill
from deepagents_cli.widgets.status import StatusBar
from deepagents_cli.widgets.welcome import WelcomeBanner

if TYPE_CHECKING:
    from langgraph.pregel import Pregel
    from textual.app import ComposeResult
    from textual.worker import Worker


class TextualTokenTracker:
    """Token tracker that updates the status bar."""

    def __init__(self, update_callback: callable, hide_callback: callable | None = None) -> None:
        """Initialize with callbacks to update the display."""
        self._update_callback = update_callback
        self._hide_callback = hide_callback
        self.current_context = 0

    def add(self, total_tokens: int, _output_tokens: int = 0) -> None:
        """Update token count from a response.

        Args:
            total_tokens: Total context tokens (input + output from usage_metadata)
            _output_tokens: Unused, kept for backwards compatibility
        """
        self.current_context = total_tokens
        self._update_callback(self.current_context)

    def reset(self) -> None:
        """Reset token count."""
        self.current_context = 0
        self._update_callback(0)

    def hide(self) -> None:
        """Hide the token display (e.g., during streaming)."""
        if self._hide_callback:
            self._hide_callback()

    def show(self) -> None:
        """Show the token display with current value (e.g., after interrupt)."""
        self._update_callback(self.current_context)


class TextualSessionState:
    """Session state for the Textual app."""

    def __init__(
        self,
        *,
        auto_approve: bool = False,
        thread_id: str | None = None,
    ) -> None:
        """Initialize session state.

        Args:
            auto_approve: Whether to auto-approve tool calls
            thread_id: Optional thread ID (generates 8-char hex if not provided)
        """
        self.auto_approve = auto_approve
        self.thread_id = thread_id if thread_id else uuid.uuid4().hex[:8]

    def reset_thread(self) -> str:
        """Reset to a new thread. Returns the new thread_id."""
        self.thread_id = uuid.uuid4().hex[:8]
        return self.thread_id


class DeepAgentsApp(App):
    """Main Textual application for deepagents-cli."""

    TITLE = "DeepAgents"
    CSS_PATH = "app.tcss"
    ENABLE_COMMAND_PALETTE = False

    # Slow down scroll speed (default is 3 lines per scroll event)
    # Using 0.25 to require 4 scroll events per line - very smooth
    SCROLL_SENSITIVITY_Y = 0.25

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "interrupt", "Interrupt", show=False, priority=True),
        Binding("ctrl+c", "quit_or_interrupt", "Quit/Interrupt", show=False),
        Binding("ctrl+d", "quit_app", "Quit", show=False, priority=True),
        Binding("ctrl+t", "toggle_auto_approve", "Toggle Auto-Approve", show=False),
        Binding(
            "shift+tab", "toggle_auto_approve", "Toggle Auto-Approve", show=False, priority=True
        ),
        Binding("ctrl+o", "toggle_tool_output", "Toggle Tool Output", show=False),
        # Approval menu keys (handled at App level for reliability)
        Binding("up", "approval_up", "Up", show=False),
        Binding("k", "approval_up", "Up", show=False),
        Binding("down", "approval_down", "Down", show=False),
        Binding("j", "approval_down", "Down", show=False),
        Binding("enter", "approval_select", "Select", show=False),
        Binding("y", "approval_yes", "Yes", show=False),
        Binding("1", "approval_yes", "Yes", show=False),
        Binding("n", "approval_no", "No", show=False),
        Binding("2", "approval_no", "No", show=False),
        Binding("a", "approval_auto", "Auto", show=False),
        Binding("3", "approval_auto", "Auto", show=False),
    ]

    def __init__(
        self,
        *,
        agent: Pregel | None = None,
        assistant_id: str | None = None,
        backend: Any = None,  # noqa: ANN401  # CompositeBackend
        agent_builder: Any = None,
        auto_approve: bool = False,
        cwd: str | Path | None = None,
        thread_id: str | None = None,
        initial_prompt: str | None = None,
        task_manager: Any = None,  # noqa: ANN401  # BackgroundTaskManager
        **kwargs: Any,
    ) -> None:
        """Initialize the DeepAgents application.

        Args:
            agent: Pre-configured LangGraph agent (optional for standalone mode)
            assistant_id: Agent identifier for memory storage
            backend: Backend for file operations
            agent_builder: Optional callback to rebuild the agent for a new model
            auto_approve: Whether to start with auto-approve enabled
            cwd: Current working directory to display
            thread_id: Optional thread ID for session persistence
            initial_prompt: Optional prompt to auto-submit when session starts
            task_manager: Optional BackgroundTaskManager for background sub-agent tasks
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._agent = agent
        self._assistant_id = assistant_id
        self._backend = backend
        self._agent_builder = agent_builder
        self._auto_approve = auto_approve
        self._cwd = str(cwd) if cwd else str(Path.cwd())
        # Avoid collision with App._thread_id
        self._lc_thread_id = thread_id
        self._initial_prompt = initial_prompt
        self._task_manager = task_manager
        self._status_bar: StatusBar | None = None
        self._chat_input: ChatInput | None = None
        self._quit_pending = False
        self._session_state: TextualSessionState | None = None
        self._ui_adapter: TextualUIAdapter | None = None
        self._pending_approval_widget: Any = None
        # Agent task tracking for interruption
        self._agent_worker: Worker[None] | None = None
        self._agent_running = False
        self._loading_widget: LoadingWidget | None = None
        self._agents_pill: AgentsPill | None = None
        self._background_agent_tasks: set[str] = set()
        self._stream_agent_namespaces: set[tuple] = set()
        self._token_tracker: TextualTokenTracker | None = None
        self._model_controller = ModelController(project_root=settings.project_root)
        self._command_registry = build_default_registry()

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        # Main chat area with scrollable transcript.
        with VerticalScroll(id="chat"):
            yield WelcomeBanner(id="welcome-banner")
            yield Container(id="messages")

        # Fixed input region above the footer/status row.
        with Container(id="bottom-app-container"):
            yield SlashCommandMenu(id="slash-command-menu")
            yield ChatInput(cwd=self._cwd, id="input-area")

        # Status bar at bottom (yielded first so it claims the bottom edge)
        yield StatusBar(cwd=self._cwd, id="status-bar")
        # Running agents pill (hidden when no agents active, docks above status bar)
        yield AgentsPill(id="agents-pill")

    async def on_mount(self) -> None:
        """Initialize components after mount."""
        self._status_bar = self.query_one("#status-bar", StatusBar)
        self._chat_input = self.query_one("#input-area", ChatInput)
        self._agents_pill = self.query_one("#agents-pill", AgentsPill)

        # Set initial auto-approve state
        if self._auto_approve:
            self._status_bar.set_auto_approve(enabled=True)

        # Create session state
        self._session_state = TextualSessionState(
            auto_approve=self._auto_approve,
            thread_id=self._lc_thread_id,
        )

        # Create token tracker that updates status bar
        self._token_tracker = TextualTokenTracker(self._update_tokens, self._hide_tokens)

        # Create UI adapter if agent is provided
        if self._agent:
            self._ui_adapter = TextualUIAdapter(
                mount_message=self._mount_message,
                update_status=self._update_status,
                request_approval=self._request_approval,
                on_auto_approve_enabled=self._on_auto_approve_enabled,
                scroll_to_bottom=self._scroll_chat_to_bottom,
                show_thinking=self._show_thinking,
                hide_thinking=self._hide_thinking,
                on_subagent_start=self._on_subagent_stream_start,
                on_subagent_end=self._on_subagent_stream_end,
            )
            self._ui_adapter.set_token_tracker(self._token_tracker)
        else:
            self._update_status("Select a model to begin")
            if self._status_bar:
                self._status_bar.set_model("no model")
            self.call_after_refresh(lambda: asyncio.create_task(self._open_model_selector()))

        # Register background task launch/completion callbacks
        if self._task_manager:
            self._task_manager.on_launch(self._on_background_task_launch)
            self._task_manager.on_complete(self._on_background_task_complete)

        # Focus the input (autocomplete is now built into ChatInput)
        self._chat_input.focus_input()
        self._chat_input.set_prompt_active(active=True)

        # Load thread history if resuming a session
        if self._lc_thread_id and self._agent:
            self.call_after_refresh(lambda: asyncio.create_task(self._load_thread_history()))
        # Auto-submit initial prompt if provided (but not when resuming - let user see history first)
        elif self._agent and self._initial_prompt and self._initial_prompt.strip():
            # Use call_after_refresh to ensure UI is fully mounted before submitting
            self.call_after_refresh(
                lambda: asyncio.create_task(self._handle_user_message(self._initial_prompt))
            )

    def _update_status(self, message: str) -> None:
        """Update the status bar with a message."""
        if self._status_bar:
            self._status_bar.set_status_message(message)

    def _update_tokens(self, count: int) -> None:
        """Update the token count in status bar."""
        if self._status_bar:
            self._status_bar.set_tokens(count)

    def _hide_tokens(self) -> None:
        """Hide the token display during streaming."""
        if self._status_bar:
            self._status_bar.hide_tokens()

    def _scroll_chat_to_bottom(self) -> None:
        """Scroll the chat area to the bottom.

        Uses a deterministic scroll-to-end to keep latest messages visible.
        """
        chat = self.query_one("#chat", VerticalScroll)
        if chat.virtual_size.height > chat.size.height:
            chat.scroll_end(animate=False)

    async def _show_thinking(self) -> None:
        """Show or reposition the thinking spinner at the bottom of messages."""
        if self._loading_widget:
            await self._loading_widget.remove()
            self._loading_widget = None

        self._loading_widget = LoadingWidget("Thinking")
        messages = self.query_one("#messages", Container)
        await messages.mount(self._loading_widget)
        self._scroll_chat_to_bottom()

    async def _hide_thinking(self) -> None:
        """Hide the thinking spinner."""
        if self._loading_widget:
            await self._loading_widget.remove()
            self._loading_widget = None

    def _on_background_task_launch(self, task_id: str) -> None:
        """Handle background task launch — update agents pill."""

        def _do():
            self._background_agent_tasks.add(task_id)
            self._refresh_agents_pill()

        self.call_later(_do)

    def _on_background_task_complete(self, task_id: str, result: dict) -> None:
        """Handle background task completion — show notification and update pill."""

        def _do():
            self._background_agent_tasks.discard(task_id)
            self._refresh_agents_pill()

            status = result.get("status", "unknown")
            duration = result.get("duration", "?")
            if status == "completed":
                msg = f"Background task '{task_id}' completed ({duration}s)"
            elif status == "failed":
                error = result.get("error", "unknown error")
                msg = f"Background task '{task_id}' failed: {error}"
            else:
                msg = f"Background task '{task_id}' finished ({status})"
            self.notify(msg, timeout=5)

        self.call_later(_do)

    def _on_subagent_stream_start(self, namespace: tuple) -> None:
        """Handle subagent stream start from adapter namespace events."""

        def _do() -> None:
            self._stream_agent_namespaces.add(namespace)
            self._refresh_agents_pill()

        self.call_later(_do)

    def _on_subagent_stream_end(self, namespace: tuple) -> None:
        """Handle subagent stream completion from adapter namespace events."""

        def _do() -> None:
            self._stream_agent_namespaces.discard(namespace)
            self._refresh_agents_pill()

        self.call_later(_do)

    def _refresh_agents_pill(self) -> None:
        """Recalculate running-agent count for the badge."""
        total = max(len(self._background_agent_tasks), len(self._stream_agent_namespaces))
        if self._agents_pill:
            # Background tasks and subagent stream namespaces can refer to the same
            # running subagent. Use the larger of the two active counts to avoid
            # double-counting overlap while still supporting stream-only signals.
            self._agents_pill.count = total
        if self._status_bar:
            self._status_bar.set_agents(total)

    def _cleanup_background_tasks(self) -> None:
        """Cancel all running background tasks."""
        if self._task_manager:
            self._task_manager.cleanup()
        self._background_agent_tasks.clear()
        self._stream_agent_namespaces.clear()
        self._refresh_agents_pill()

    async def _request_approval(
        self,
        action_request: Any,  # noqa: ANN401
        assistant_id: str | None,
    ) -> asyncio.Future:
        """Request user approval inline in the messages area.

        Returns a Future that resolves to the user's decision.
        Mounts ApprovalMenu in the messages area (inline with chat).
        ChatInput stays visible - user can still see it.

        If another approval is already pending, queue this one.
        """
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future = loop.create_future()

        # If there's already a pending approval, wait for it to complete first
        if self._pending_approval_widget is not None:
            while self._pending_approval_widget is not None:  # noqa: ASYNC110
                await asyncio.sleep(0.1)

        # Create menu with unique ID to avoid conflicts
        unique_id = f"approval-menu-{uuid.uuid4().hex[:8]}"
        menu = ApprovalMenu(action_request, assistant_id, id=unique_id)
        menu.set_future(result_future)

        # Store reference
        self._pending_approval_widget = menu

        # Mount approval inline in messages area (not replacing ChatInput)
        try:
            messages = self.query_one("#messages", Container)
            await messages.mount(menu)
            self._scroll_chat_to_bottom()
            # Focus approval menu
            self.call_after_refresh(menu.focus)
        except Exception as e:
            self._pending_approval_widget = None
            if not result_future.done():
                result_future.set_exception(e)

        return result_future

    def _on_auto_approve_enabled(self) -> None:
        """Callback when auto-approve mode is enabled via HITL."""
        self._auto_approve = True
        if self._status_bar:
            self._status_bar.set_auto_approve(enabled=True)
        if self._session_state:
            self._session_state.auto_approve = True

    async def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle submitted input from ChatInput widget."""
        value = event.value
        mode = event.mode

        # Reset quit pending state on any input
        self._quit_pending = False

        # Handle different modes
        if mode == "bash":
            # Bash command - strip the ! prefix
            await self._handle_bash_command(value.removeprefix("!"))
        elif mode == "command":
            # Slash command
            await self._handle_command(value)
        else:
            # Normal message - will be sent to agent
            await self._handle_user_message(value)

    def on_chat_input_mode_changed(self, event: ChatInput.ModeChanged) -> None:
        """Update status bar when input mode changes."""
        if self._status_bar:
            self._status_bar.set_mode(event.mode)

    def on_chat_input_slash_menu_update(self, event: ChatInput.SlashMenuUpdate) -> None:
        """Handle slash menu updates from ChatInput."""
        try:
            menu = self.query_one("#slash-command-menu", SlashCommandMenu)
        except NoMatches:
            return
        if event.visible and event.suggestions:
            menu.update_suggestions(event.suggestions, event.selected_index)
        else:
            menu.hide_menu()

    async def on_approval_menu_decided(
        self,
        event: Any,  # noqa: ANN401, ARG002
    ) -> None:
        """Handle approval menu decision - remove from messages and refocus input."""
        # Remove ApprovalMenu using stored reference
        if self._pending_approval_widget:
            await self._pending_approval_widget.remove()
            self._pending_approval_widget = None

        # Refocus the chat input
        if self._chat_input:
            self.call_after_refresh(self._chat_input.focus_input)

    async def _handle_bash_command(self, command: str) -> None:
        """Handle a bash command (! prefix).

        Args:
            command: The bash command to execute
        """
        # Mount user message showing the bash command
        await self._mount_message(UserMessage(f"!{command}"))

        # Execute the bash command (shell=True is intentional for user-requested bash)
        try:
            result = await asyncio.to_thread(  # noqa: S604
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=60,
            )
            output = result.stdout.strip()
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr.strip()}"

            if output:
                # Display output as assistant message (uses markdown for code blocks)
                msg = AssistantMessage(f"```\n{output}\n```")
                await self._mount_message(msg)
                await msg.write_initial_content()
            else:
                await self._mount_message(SystemMessage("Command completed (no output)"))

            if result.returncode != 0:
                await self._mount_message(ErrorMessage(f"Exit code: {result.returncode}"))

            # Scroll to show the output
            self._scroll_chat_to_bottom()

        except subprocess.TimeoutExpired:
            await self._mount_message(ErrorMessage("Command timed out (60s limit)"))
        except OSError as e:
            await self._mount_message(ErrorMessage(str(e)))

    @staticmethod
    def _strip_model_prefix(model_name: str) -> str:
        """Normalize model name by stripping provider prefixes."""
        return ModelController.strip_model_prefix(model_name)

    @staticmethod
    def _truncate_model_name(name: str) -> str:
        """Truncate model name to last meaningful segment.

        E.g. 'claude-opus-4-6' -> 'opus-4-6', 'gpt-4o-mini' -> 'gpt-4o-mini'
        """
        return ModelController.truncate_model_name(name)

    def _format_model_entry(self, entry: ModelEntry, index: int | None = None) -> str:
        return self._model_controller.format_model_entry(entry, index=index)

    def _available_tool_names(self) -> set[str]:
        """Best-effort tool capability lookup for the current session."""
        names: set[str] = set()
        for source in (self._backend, self._agent):
            tool_names = getattr(source, "available_tool_names", None)
            if isinstance(tool_names, set):
                names.update(str(item) for item in tool_names if isinstance(item, str))
            elif isinstance(tool_names, (list, tuple)):
                names.update(str(item) for item in tool_names if isinstance(item, str))
        return names

    def _build_model_catalog(self) -> list[ModelEntry]:
        return self._model_controller.build_model_catalog()

    async def _switch_model(self, model_name: str, entry: ModelEntry | None = None) -> None:
        if self._agent_running:
            await self._mount_message(
                SystemMessage("Cannot switch models while the agent is running.")
            )
            return
        if not self._agent_builder:
            await self._mount_message(
                SystemMessage("Model switching is not available in this session.")
            )
            return

        normalized = self._model_controller.strip_model_prefix(model_name)
        auto_approve = self._session_state.auto_approve if self._session_state else False

        reasoning_override = entry.reasoning_effort if entry else None
        service_tier_override = entry.service_tier if entry else None

        try:
            agent, backend, task_manager = self._agent_builder(
                normalized,
                auto_approve_override=auto_approve,
                reasoning_effort_override=reasoning_override,
                service_tier_override=service_tier_override,
            )
        except SystemExit:
            await self._mount_message(
                ErrorMessage("Model switch failed. Check API keys and model name.")
            )
            return
        except Exception as exc:
            await self._mount_message(ErrorMessage(f"Model switch failed: {exc}"))
            return

        # Clean up old background tasks before switching
        self._cleanup_background_tasks()

        self._agent = agent
        self._backend = backend
        self._task_manager = task_manager
        if self._task_manager:
            self._task_manager.on_launch(self._on_background_task_launch)
            self._task_manager.on_complete(self._on_background_task_complete)
        self._background_agent_tasks.clear()
        self._stream_agent_namespaces.clear()
        self._refresh_agents_pill()
        if self._ui_adapter is None:
            self._ui_adapter = TextualUIAdapter(
                mount_message=self._mount_message,
                update_status=self._update_status,
                request_approval=self._request_approval,
                on_auto_approve_enabled=self._on_auto_approve_enabled,
                scroll_to_bottom=self._scroll_chat_to_bottom,
                show_thinking=self._show_thinking,
                hide_thinking=self._hide_thinking,
                on_subagent_start=self._on_subagent_stream_start,
                on_subagent_end=self._on_subagent_stream_end,
            )
            self._ui_adapter.set_token_tracker(self._token_tracker)
        if self._token_tracker:
            self._token_tracker.reset()
        raw_name = entry.display_name if entry else (settings.model_name or normalized)
        display_name = self._model_controller.truncate_model_name(raw_name)
        if self._status_bar:
            self._status_bar.set_model(display_name)
        await self._mount_message(SystemMessage(f"Active model: {display_name}"))

        if entry is not None:
            self._model_controller.persist_active_selection(entry)

    def _format_debug_model(self) -> list[str]:
        return self._model_controller.format_debug_model()

    def _handle_model_selector_result(self, result: ModelEntry | None) -> None:
        self._model_controller.set_model_selector_open(is_open=False)
        if result is None:
            return
        self.run_worker(self._switch_model(result.id, result), exclusive=False)

    async def _open_model_selector(self) -> None:
        if self._model_controller.model_selector_open:
            return
        entries = self._build_model_catalog()
        if not entries:
            await self._mount_message(
                SystemMessage(
                    "No model catalog found. Add ~/.deepagents/models.json "
                    "or set model.active in ~/.deepagents/settings.json."
                )
            )
            return
        self._model_controller.set_model_selector_open(is_open=True)
        current_key = None
        if settings.model_provider and settings.model_name:
            current_key = f"{settings.model_provider}:{settings.model_name}"
        screen = ModelSelectorScreen(entries=entries, current_model_id=current_key)
        self.push_screen(screen, self._handle_model_selector_result)

    async def _mount_user_text(self, content: str) -> None:
        await self._mount_message(UserMessage(content))

    async def _mount_system_text(self, content: str) -> None:
        await self._mount_message(SystemMessage(content))

    async def _mount_error_text(self, content: str) -> None:
        await self._mount_message(ErrorMessage(content))

    def _reset_tokens(self) -> None:
        if self._token_tracker:
            self._token_tracker.reset()

    def _reset_thread(self) -> str | None:
        if not self._session_state:
            return None
        return self._session_state.reset_thread()

    def _current_thread_id(self) -> str | None:
        if not self._session_state:
            return None
        return self._session_state.thread_id

    def _current_context_tokens(self) -> int:
        if not self._token_tracker:
            return 0
        return self._token_tracker.current_context

    async def _handle_command(self, command: str) -> None:
        """Handle a slash command.

        Args:
            command: The slash command (including /)
        """
        context = CommandContext(
            command=command,
            normalized=command.lower().strip(),
            mount_user=self._mount_user_text,
            mount_system=self._mount_system_text,
            mount_error=self._mount_error_text,
            handle_user_message=self._handle_user_message,
            clear_messages=self._clear_messages,
            clear_status=lambda: self._update_status(""),
            exit_app=self.exit,
            reset_tokens=self._reset_tokens,
            reset_thread=self._reset_thread,
            current_thread_id=self._current_thread_id,
            current_context_tokens=self._current_context_tokens,
            open_model_selector=self._open_model_selector,
            switch_model=self._switch_model,
            model_controller=self._model_controller,
            available_tool_names=self._available_tool_names,
        )
        handled = await self._command_registry.dispatch(context)
        if not handled:
            await self._mount_user_text(command)
            await self._mount_system_text(f"Unknown command: {context.normalized}")

    async def _handle_user_message(self, message: str) -> None:
        """Handle a user message to send to the agent.

        Args:
            message: The user's message
        """
        # Mount the user message
        await self._mount_message(UserMessage(message))

        # Check if agent is available
        if self._agent and self._ui_adapter and self._session_state:
            self._agent_running = True

            # Disable submission while agent is working (user can still type)
            if self._chat_input:
                self._chat_input.set_cursor_active(active=False)
                self._chat_input.set_submit_enabled(enabled=False)
                self._chat_input.set_prompt_active(active=False)

            # Use run_worker to avoid blocking the main event loop
            # This allows the UI to remain responsive during agent execution
            self._agent_worker = self.run_worker(
                self._run_agent_task(message),
                exclusive=False,
            )
        else:
            await self._mount_message(
                SystemMessage("No active model configured. Use /model to select one.")
            )
            await self._open_model_selector()

    async def _run_agent_task(self, message: str) -> None:
        """Run the agent task in a background worker.

        This runs in a worker thread so the main event loop stays responsive.
        """
        try:
            await execute_task_textual(
                user_input=message,
                agent=self._agent,
                assistant_id=self._assistant_id,
                session_state=self._session_state,
                adapter=self._ui_adapter,
                backend=self._backend,
            )
        except Exception as e:
            await self._mount_message(ErrorMessage(f"Agent error: {e}"))
        finally:
            # Clean up loading widget and agent state
            await self._cleanup_agent_task()

    async def _cleanup_agent_task(self) -> None:
        """Clean up after agent task completes or is cancelled."""
        self._agent_running = False
        self._agent_worker = None

        # Remove thinking spinner if present
        await self._hide_thinking()

        # Re-enable submission now that agent is done
        if self._chat_input:
            self._chat_input.set_cursor_active(active=True)
            self._chat_input.set_submit_enabled(enabled=True)
            self._chat_input.set_prompt_active(active=True)

        # Ensure token display is restored (in case of early cancellation)
        if self._token_tracker:
            self._token_tracker.show()

    async def _load_thread_history(self) -> None:
        """Load and render message history when resuming a thread.

        This retrieves the checkpoint state from the agent and converts
        stored messages into UI widgets.
        """
        if not self._agent or not self._lc_thread_id:
            return

        config = {"configurable": {"thread_id": self._lc_thread_id}}

        try:
            # Get the state snapshot from the agent
            state = await self._agent.aget_state(config)
            if not state or not state.values:
                return

            messages = state.values.get("messages", [])
            if not messages:
                return

            # Track tool calls from AIMessages to match with ToolMessages
            pending_tool_calls: dict[str, dict] = {}

            for msg in messages:
                if isinstance(msg, HumanMessage):
                    # Skip system messages that were auto-injected
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    if content.startswith("[SYSTEM]"):
                        continue
                    await self._mount_message(UserMessage(content))

                elif isinstance(msg, AIMessage):
                    # Render text content if present
                    content = msg.content
                    if isinstance(content, str) and content.strip():
                        widget = AssistantMessage(content)
                        await self._mount_message(widget)
                        await widget.write_initial_content()

                    # Track tool calls for later matching with ToolMessages
                    tool_calls = getattr(msg, "tool_calls", [])
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        if tc_id:
                            pending_tool_calls[tc_id] = {
                                "name": tc.get("name", "unknown"),
                                "args": tc.get("args", {}),
                            }
                            # Mount tool call widget
                            tool_widget = ToolCallMessage(
                                tc.get("name", "unknown"),
                                tc.get("args", {}),
                            )
                            await self._mount_message(tool_widget)
                            # Store widget reference for result matching
                            pending_tool_calls[tc_id]["widget"] = tool_widget

                elif isinstance(msg, ToolMessage):
                    # Match with pending tool call and show result
                    tc_id = getattr(msg, "tool_call_id", None)
                    if tc_id and tc_id in pending_tool_calls:
                        tool_info = pending_tool_calls.pop(tc_id)
                        widget = tool_info.get("widget")
                        if widget:
                            status = getattr(msg, "status", "success")
                            content = (
                                msg.content if isinstance(msg.content, str) else str(msg.content)
                            )
                            if status == "success":
                                widget.set_success(content)
                            else:
                                widget.set_error(content)

            # Mark any unmatched tool calls as interrupted (no ToolMessage result)
            for tool_info in pending_tool_calls.values():
                widget = tool_info.get("widget")
                if widget:
                    widget.set_rejected()  # Shows as interrupted/rejected in UI

            # Show system message indicating this is a resumed session
            await self._mount_message(SystemMessage(f"Resumed session: {self._lc_thread_id}"))

            # Scroll to bottom after UI renders
            def scroll_to_end() -> None:
                chat = self.query_one("#chat", VerticalScroll)
                chat.scroll_end(animate=False)

            self.call_after_refresh(scroll_to_end)

        except Exception as e:
            # Don't fail the app if history loading fails
            await self._mount_message(SystemMessage(f"Could not load history: {e}"))

    async def _mount_message(self, widget: Static) -> None:
        """Mount a message widget to the messages area.

        Args:
            widget: The message widget to mount
        """
        messages = self.query_one("#messages", Container)
        await messages.mount(widget)
        # Keep latest message visible after layout settles.
        self.call_after_refresh(self._scroll_chat_to_bottom)

    async def _clear_messages(self) -> None:
        """Clear the messages area and cancel background tasks."""
        self._cleanup_background_tasks()
        try:
            messages = self.query_one("#messages", Container)
            await messages.remove_children()
        except NoMatches:
            # Widget not found - can happen during shutdown
            pass

    def action_quit_or_interrupt(self) -> None:
        """Handle Ctrl+C - interrupt agent, reject approval, or quit on double press.

        Priority order:
        1. If agent is running, interrupt it (preserve input)
        2. If approval menu is active, reject it
        3. If double press (quit_pending), quit
        4. Otherwise show quit hint
        """
        # If agent is running, interrupt it
        if self._agent_running and self._agent_worker:
            self._agent_worker.cancel()
            self._cleanup_background_tasks()
            self._quit_pending = False
            return

        # If approval menu is active, reject it
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_reject()
            self._quit_pending = False
            return

        # Double Ctrl+C to quit
        if self._quit_pending:
            self._cleanup_background_tasks()
            self.exit()
        else:
            self._quit_pending = True
            self.notify("Press Ctrl+C again to quit", timeout=3)

    def action_interrupt(self) -> None:
        """Handle escape key - interrupt agent, reject approval, or dismiss modal.

        This is the primary way to stop a running agent.
        """
        # If agent is running, interrupt it
        if self._agent_running and self._agent_worker:
            self._agent_worker.cancel()
            self._cleanup_background_tasks()
            return

        # If approval menu is active, reject it
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_reject()
            return

        # If model selector (or any modal) is open, dismiss it
        if self._model_controller.model_selector_open:
            self._model_controller.set_model_selector_open(is_open=False)
            self.screen.dismiss(None)

    def action_quit_app(self) -> None:
        """Handle quit action (Ctrl+D)."""
        self._cleanup_background_tasks()
        self.exit()

    def action_toggle_auto_approve(self) -> None:
        """Toggle auto-approve mode."""
        self._auto_approve = not self._auto_approve
        if self._status_bar:
            self._status_bar.set_auto_approve(enabled=self._auto_approve)
        if self._session_state:
            self._session_state.auto_approve = self._auto_approve

    def action_toggle_tool_output(self) -> None:
        """Toggle expand/collapse of all tool outputs."""
        try:
            tool_messages = list(self.query(ToolCallMessage))
            outputs = [m for m in tool_messages if m.has_output]
            if not outputs:
                return
            target_state = not outputs[0]._expanded
            for tool_msg in outputs:
                if tool_msg._expanded != target_state:
                    tool_msg.toggle_output()
        except Exception:
            pass

    # Approval menu action handlers (delegated from App-level bindings)
    # NOTE: These only activate when approval widget is pending AND input is not focused
    def action_approval_up(self) -> None:
        """Handle up arrow in approval menu."""
        # Only handle if approval is active (input handles its own up for history/completion)
        if self._pending_approval_widget and not self._is_input_focused():
            self._pending_approval_widget.action_move_up()

    def action_approval_down(self) -> None:
        """Handle down arrow in approval menu."""
        if self._pending_approval_widget and not self._is_input_focused():
            self._pending_approval_widget.action_move_down()

    def action_approval_select(self) -> None:
        """Handle enter in approval menu."""
        # Only handle if approval is active AND input is not focused
        if self._pending_approval_widget and not self._is_input_focused():
            self._pending_approval_widget.action_select()

    def _is_input_focused(self) -> bool:
        """Check if the chat input (or its text area) has focus."""
        if not self._chat_input:
            return False
        focused = self.focused
        if focused is None:
            return False
        # Check if focused widget is the text area inside chat input
        return focused.id == "chat-input" or focused in self._chat_input.walk_children()

    def action_approval_yes(self) -> None:
        """Handle yes/1 in approval menu."""
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_approve()

    def action_approval_no(self) -> None:
        """Handle no/2 in approval menu."""
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_reject()

    def action_approval_auto(self) -> None:
        """Handle auto/3 in approval menu."""
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_auto()

    def action_approval_escape(self) -> None:
        """Handle escape in approval menu - reject."""
        if self._pending_approval_widget:
            self._pending_approval_widget.action_select_reject()

    def on_click(self, event: Click) -> None:
        """Focus input when appropriate without stealing focus from active surfaces."""
        if not self._chat_input:
            return

        # Never steal focus while a modal is active.
        if self._model_controller.model_selector_open:
            return

        target = getattr(event, "widget", None)
        if target is not None:
            if target is self._chat_input or target in self._chat_input.walk_children():
                return
            if self._pending_approval_widget and (
                target is self._pending_approval_widget
                or target in self._pending_approval_widget.walk_children()
            ):
                return

        self.call_after_refresh(self._chat_input.focus_input)

    def on_mouse_up(self, event: MouseUp) -> None:  # noqa: ARG002
        """Copy selection to clipboard on mouse release."""
        copy_selection_to_clipboard(self)


async def run_textual_app(
    *,
    agent: Pregel | None = None,
    assistant_id: str | None = None,
    backend: Any = None,  # noqa: ANN401  # CompositeBackend
    agent_builder: Any = None,
    auto_approve: bool = False,
    cwd: str | Path | None = None,
    thread_id: str | None = None,
    initial_prompt: str | None = None,
    task_manager: Any = None,  # noqa: ANN401  # BackgroundTaskManager
) -> None:
    """Run the Textual application.

    Args:
        agent: Pre-configured LangGraph agent (optional)
        assistant_id: Agent identifier for memory storage
        backend: Backend for file operations
        agent_builder: Optional callback to rebuild the agent for a new model
        auto_approve: Whether to start with auto-approve enabled
        cwd: Current working directory to display
        thread_id: Optional thread ID for session persistence
        initial_prompt: Optional prompt to auto-submit when session starts
        task_manager: Optional BackgroundTaskManager for background sub-agent tasks
    """
    app = DeepAgentsApp(
        agent=agent,
        assistant_id=assistant_id,
        backend=backend,
        agent_builder=agent_builder,
        auto_approve=auto_approve,
        cwd=cwd,
        thread_id=thread_id,
        initial_prompt=initial_prompt,
        task_manager=task_manager,
    )
    await app.run_async()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_textual_app())
