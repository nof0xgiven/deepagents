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
        background: #111111;
        padding: 0 1;
    }

    StatusBar .status-mode {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-mode.normal {
        display: none;
    }

    StatusBar .status-mode.bash {
        color: #3f3f46;
    }

    StatusBar .status-mode.command {
        color: #3f3f46;
    }

    StatusBar .status-separator {
        width: auto;
        color: #3f3f46;
    }

    StatusBar .status-auto-approve {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-message {
        width: 1fr;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-message.thinking {
        color: #71717a;
    }

    StatusBar .status-tokens {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-model {
        width: auto;
        padding: 0 1;
        color: #71717a;
    }
    """

    mode: reactive[str] = reactive("normal", init=False)
    status_message: reactive[str] = reactive("", init=False)
    auto_approve: reactive[bool] = reactive(default=False, init=False)
    cwd: reactive[str] = reactive("", init=False)
    tokens: reactive[int] = reactive(0, init=False)

    def __init__(self, cwd: str | Path | None = None, **kwargs: Any) -> None:
        """Initialize the status bar.

        Args:
            cwd: Current working directory to display
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        # Store initial cwd - will be used in compose()
        self._initial_cwd = str(cwd) if cwd else str(Path.cwd())

    def compose(self) -> ComposeResult:
        """Compose the status bar layout."""
        yield Static("", classes="status-mode normal", id="mode-indicator")
        yield Static(" · ", classes="status-separator")
        yield Static(
            "manual",
            classes="status-auto-approve",
            id="auto-approve-indicator",
        )
        yield Static(" · ", classes="status-separator")
        yield Static("", classes="status-message", id="status-message")
        yield Static("", classes="status-tokens", id="tokens-display")
        yield Static(" · ", classes="status-separator")
        yield Static(settings.model_name or "", classes="status-model", id="model-display")

    def on_mount(self) -> None:
        """Set reactive values after mount to trigger watchers safely."""
        self.cwd = self._initial_cwd

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
        if new_value:
            indicator.update("auto")
        else:
            indicator.update("manual")

    def watch_cwd(self, new_value: str) -> None:
        """Update cwd display when it changes."""
        try:
            display = self.query_one("#cwd-display", Static)
        except NoMatches:
            return
        display.update(self._format_cwd(new_value))

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

    def _format_cwd(self, cwd_path: str = "") -> str:
        """Format the current working directory for display."""
        path = Path(cwd_path or self.cwd or self._initial_cwd)
        try:
            # Try to use ~ for home directory
            home = Path.home()
            if path.is_relative_to(home):
                return "~/" + str(path.relative_to(home))
        except (ValueError, RuntimeError):
            pass
        return str(path)

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
        try:
            display = self.query_one("#tokens-display", Static)
        except NoMatches:
            return

        if new_value > 0:
            # Format with K suffix for thousands
            if new_value >= 1000:
                display.update(f"{new_value / 1000:.1f}K tokens")
            else:
                display.update(f"{new_value} tokens")
        else:
            display.update("")

    def set_tokens(self, count: int) -> None:
        """Set the token count.

        Args:
            count: Current context token count
        """
        self.tokens = count

    def set_model(self, model_name: str) -> None:
        """Update the displayed model name."""
        try:
            display = self.query_one("#model-display", Static)
        except NoMatches:
            return
        display.update(model_name)

    def hide_tokens(self) -> None:
        """Hide the token display (e.g., during streaming)."""
        self.query_one("#tokens-display", Static).update("")
