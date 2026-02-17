"""Status bar widget for deepagents-cli."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Static

from deepagents_cli.config import settings

if TYPE_CHECKING:
    from textual.app import ComposeResult


class StatusBar(Horizontal):
    """Status bar showing mode, auto-approve status, and working directory."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: transparent;
        padding: 0 1;
    }

    StatusBar .status-mode {
        width: auto;
        padding: 0 1;
        color: #d0dbe7;
    }

    StatusBar .status-mode.normal {
        display: none;
    }

    StatusBar .status-mode.bash {
        color: #f4cf7e;
    }

    StatusBar .status-mode.command {
        color: #8cd8ff;
    }

    StatusBar .status-auto-approve {
        width: auto;
        padding: 0 1;
    }

    StatusBar .status-auto-approve.auto {
        color: #72d69f;
    }

    StatusBar .status-auto-approve.manual {
        color: #d0dbe7;
    }

    StatusBar .status-message {
        width: 1fr;
        padding: 0 1;
        color: #d0dbe7;
    }

    StatusBar .status-message.thinking {
        color: #8cd8ff;
    }

    StatusBar .status-tokens {
        width: auto;
        padding: 0 1;
        color: #d0dbe7;
    }

    StatusBar .status-agents {
        width: auto;
        padding: 0 1;
        color: #d0dbe7;
    }

    StatusBar .status-model {
        width: auto;
        padding: 0 1;
        color: #d0dbe7;
    }
    """

    mode: reactive[str] = reactive("normal", init=False)
    status_message: reactive[str] = reactive("", init=False)
    auto_approve: reactive[bool] = reactive(default=False, init=False)
    tokens: reactive[int] = reactive(0, init=False)
    agents: reactive[int] = reactive(0, init=False)

    def __init__(self, cwd: str | Path | None = None, **kwargs: Any) -> None:
        """Initialize the status bar.

        Args:
            cwd: Current working directory to display
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._tokens_hidden = False

    def compose(self) -> ComposeResult:
        """Compose the status bar layout."""
        # Left group: mode + auto-approve
        yield Static("", classes="status-mode normal", id="mode-indicator")
        yield Static(
            "manual",
            classes="status-auto-approve manual",
            id="auto-approve-indicator",
        )
        # Center: status message (flexible width)
        yield Static("", classes="status-message", id="status-message")
        # Right group: tokens | agents | model
        yield Static("tokens: 0", classes="status-tokens", id="tokens-display")
        yield Static("", classes="status-agents", id="agents-display")
        yield Static(
            f"model: {settings.model_name or 'none'}",
            classes="status-model",
            id="model-display",
        )

    def watch_mode(self, mode: str) -> None:
        """Update mode indicator when mode changes."""
        try:
            indicator = self.query_one("#mode-indicator", Static)
        except NoMatches:
            return
        indicator.remove_class("normal", "bash", "command")

        if mode == "bash":
            indicator.update("bash")
            indicator.add_class("bash")
        elif mode == "command":
            indicator.update("cmd")
            indicator.add_class("command")
        else:
            indicator.update("")
            indicator.add_class("normal")

    def watch_auto_approve(self, new_value: bool) -> None:  # noqa: FBT001
        """Update auto-approve indicator when state changes."""
        try:
            indicator = self.query_one("#auto-approve-indicator", Static)
        except NoMatches:
            return
        indicator.remove_class("manual", "auto")
        if new_value:
            indicator.update("auto")
            indicator.add_class("auto")
        else:
            indicator.update("manual")
            indicator.add_class("manual")

    def watch_status_message(self, new_value: str) -> None:
        """Update status message display."""
        try:
            msg_widget = self.query_one("#status-message", Static)
        except NoMatches:
            return

        msg_widget.remove_class("thinking")
        if new_value:
            msg_widget.update(new_value)
            if "thinking" in new_value.lower() or "executing" in new_value.lower():
                msg_widget.add_class("thinking")
        else:
            msg_widget.update("")

    def set_mode(self, mode: str) -> None:
        """Set the current input mode.

        Args:
            mode: One of "normal", "bash", or "command"
        """
        self.mode = mode

    def set_auto_approve(self, *, enabled: bool) -> None:
        """Set the auto-approve state.

        Args:
            enabled: Whether auto-approve is enabled
        """
        self.auto_approve = enabled

    def set_status_message(self, message: str) -> None:
        """Set the status message.

        Args:
            message: Status message to display (empty string to clear)
        """
        self.status_message = message

    def watch_tokens(self, new_value: int) -> None:
        """Update token display when count changes."""
        self._tokens_hidden = False
        self._render_tokens(new_value)

    def _render_tokens(self, count: int) -> None:
        """Render the token display regardless of reactive changes."""
        try:
            display = self.query_one("#tokens-display", Static)
        except NoMatches:
            return

        # Format with K suffix for thousands.
        if count >= 1000:
            display.update(f"tokens: {count / 1000:.1f}K")
        else:
            display.update(f"tokens: {count}")

    def set_tokens(self, count: int) -> None:
        """Set the token count.

        Args:
            count: Current context token count
        """
        if count == self.tokens and self._tokens_hidden:
            self._tokens_hidden = False
            self._render_tokens(count)
            return
        self.tokens = count

    def set_model(self, model_name: str) -> None:
        """Update the displayed model name."""
        try:
            display = self.query_one("#model-display", Static)
        except NoMatches:
            return
        display.update(f"model: {model_name}")

    def watch_agents(self, new_value: int) -> None:
        """Update agent count display in footer."""
        try:
            display = self.query_one("#agents-display", Static)
        except NoMatches:
            return
        if new_value > 0:
            display.update(f"agents: {new_value}")
            display.styles.display = "block"
        else:
            display.update("")
            display.styles.display = "none"

    def set_agents(self, count: int) -> None:
        """Set running agents count."""
        self.agents = max(0, count)

    def hide_tokens(self) -> None:
        """Hide the token display (e.g., during streaming)."""
        self._tokens_hidden = True
        try:
            display = self.query_one("#tokens-display", Static)
        except NoMatches:
            return
        display.update("tokens: --")
