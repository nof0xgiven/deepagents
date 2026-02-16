"""Message widgets for deepagents-cli."""

from __future__ import annotations

from time import time
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Markdown, Static
from textual.widgets._markdown import MarkdownStream

from deepagents_cli.ui import format_tool_display
from deepagents_cli.widgets.diff import format_diff_textual
from deepagents_cli.widgets.loading import BrailleSpinner

if TYPE_CHECKING:
    from textual.app import ComposeResult

# Maximum number of tool arguments to display inline
_MAX_INLINE_ARGS = 3
_TEXT_PRIMARY = "#f4f8fc"
_TEXT_SECONDARY = "#d0dbe7"
_TEXT_MUTED = "#9aa8b7"
_TEXT_HINT = "#8898a8"
_ACCENT = "#8cd8ff"
_SUCCESS = "#72d69f"
_ERROR = "#ff7a7a"


class UserMessage(Static):
    """Widget displaying a user message."""

    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    """

    def __init__(self, content: str, **kwargs: Any) -> None:
        """Initialize a user message.

        Args:
            content: The message content
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._content = content

    def compose(self) -> ComposeResult:
        """Compose the user message layout."""
        # Use Text object to combine styled prefix with unstyled user content
        text = Text()
        text.append("> ", style=_TEXT_MUTED)
        text.append(self._content, style=_TEXT_PRIMARY)
        yield Static(text)


class AssistantMessage(Vertical):
    """Widget displaying an assistant message with markdown support.

    Uses MarkdownStream for smoother streaming instead of re-rendering
    the full content on each update.
    """

    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        padding: 1 2;
        margin: 1 0;
        background: transparent;
        border-left: solid #98a8b8 22%;
    }

    AssistantMessage Markdown {
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, content: str = "", **kwargs: Any) -> None:
        """Initialize an assistant message.

        Args:
            content: Initial markdown content
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._content = content
        self._markdown: Markdown | None = None
        self._stream: MarkdownStream | None = None

    def compose(self) -> ComposeResult:
        """Compose the assistant message layout."""
        yield Markdown("", id="assistant-content")

    def on_mount(self) -> None:
        """Store reference to markdown widget."""
        self._markdown = self.query_one("#assistant-content", Markdown)

    def _get_markdown(self) -> Markdown:
        """Get the markdown widget, querying if not cached."""
        if self._markdown is None:
            self._markdown = self.query_one("#assistant-content", Markdown)
        return self._markdown

    def _ensure_stream(self) -> MarkdownStream:
        """Ensure the markdown stream is initialized."""
        if self._stream is None:
            self._stream = Markdown.get_stream(self._get_markdown())
        return self._stream

    async def append_content(self, text: str) -> None:
        """Append content to the message (for streaming).

        Uses MarkdownStream for smoother rendering instead of re-rendering
        the full content on each chunk.

        Args:
            text: Text to append
        """
        if not text:
            return
        self._content += text
        stream = self._ensure_stream()
        await stream.write(text)

    async def write_initial_content(self) -> None:
        """Write initial content if provided at construction time."""
        if self._content:
            stream = self._ensure_stream()
            await stream.write(self._content)

    async def stop_stream(self) -> None:
        """Stop the streaming and finalize the content."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None

    async def set_content(self, content: str) -> None:
        """Set the full message content.

        This stops any active stream and sets content directly.

        Args:
            content: The markdown content to display
        """
        await self.stop_stream()
        self._content = content
        if self._markdown:
            await self._markdown.update(content)


class ToolCallMessage(Vertical):
    """Widget displaying a tool call with collapsible output.

    Tool outputs are shown as a 3-line preview by default.
    Press Ctrl+O to expand/collapse the full output.
    """

    DEFAULT_CSS = """
    ToolCallMessage {
        height: auto;
        padding: 1 1;
        margin: 1 0 0 0;
        background: transparent;
    }

    ToolCallMessage .tool-header {
        color: #d8e4f0;
    }

    ToolCallMessage .tool-args {
        color: #9fb0c0;
        margin-left: 2;
    }

    ToolCallMessage .tool-status {
        margin-left: 2;
    }

    ToolCallMessage .tool-status.pending {
        color: #a8b8c8;
    }

    ToolCallMessage .tool-status.success {
        color: #9fb0c0;
    }

    ToolCallMessage .tool-status.error {
        color: #ff7a7a;
    }

    ToolCallMessage .tool-status.rejected {
        color: #a8b8c8;
    }

    ToolCallMessage .tool-status.executing {
        color: #8cd8ff;
    }

    ToolCallMessage .tool-output {
        margin-left: 2;
        margin-top: 1;
        padding: 1;
        background: transparent;
        color: #d0dbe7;
        border-left: solid #8cd8ff 45%;
        max-height: 20;
        overflow-y: auto;
    }

    ToolCallMessage .tool-output-preview {
        margin-left: 2;
        color: #d0dbe7;
    }

    ToolCallMessage .tool-output-hint {
        margin-left: 2;
        color: #8b99a8;
    }
    """

    # Max lines/chars to show in preview mode
    _PREVIEW_LINES = 6
    _PREVIEW_CHARS = 420

    # Tools that show an executing indicator (long-running)
    _LONG_RUNNING_TOOLS = {"task"}

    def __init__(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a tool call message.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments (optional)
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._args = args or {}
        self._status = "pending"
        self._output: str = ""
        self._expanded: bool = False
        # Widget references (set in on_mount)
        self._status_widget: Static | None = None
        self._preview_widget: Static | None = None
        self._hint_widget: Static | None = None
        self._full_widget: Static | None = None
        # Executing state for long-running tools
        self._executing_timer: Timer | None = None
        self._executing_start_time: float = 0.0
        self._spinner: BrailleSpinner | None = None

    def compose(self) -> ComposeResult:
        """Compose the tool call message layout."""
        tool_label = format_tool_display(self._tool_name, self._args)
        yield Static(
            f"{tool_label}",
            classes="tool-header",
        )
        args = self._filtered_args()
        if args:
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:_MAX_INLINE_ARGS])
            if len(args) > _MAX_INLINE_ARGS:
                args_str += ", ..."
            yield Static(f"({args_str})", classes="tool-args")
        # Status - hidden by default, only shown for errors/rejections
        yield Static("", classes="tool-status", id="status")
        # Output area - hidden initially, shown when output is set
        # Use markup=False for output content to prevent Rich markup injection
        yield Static("", classes="tool-output-preview", id="output-preview", markup=False)
        yield Static("", classes="tool-output-hint", id="output-hint")  # hint uses our markup
        yield Static("", classes="tool-output", id="output-full", markup=False)

    def on_mount(self) -> None:
        """Cache widget references and hide status/output areas initially."""
        self._status_widget = self.query_one("#status", Static)
        self._preview_widget = self.query_one("#output-preview", Static)
        self._hint_widget = self.query_one("#output-hint", Static)
        self._full_widget = self.query_one("#output-full", Static)
        self._status_widget.display = False
        self._preview_widget.display = False
        self._hint_widget.display = False
        self._full_widget.display = False
        if self._tool_name in self._LONG_RUNNING_TOOLS:
            self._start_executing()

    def _start_executing(self) -> None:
        """Start the executing indicator for long-running tools."""
        self._executing_start_time = time()
        self._spinner = BrailleSpinner()
        if self._status_widget:
            self._status_widget.update(f"{self._spinner.current_frame()} working... (0s)")
            self._status_widget.add_class("executing")
            self._status_widget.display = True
        self._executing_timer = self.set_interval(0.1, self._update_executing)

    def _update_executing(self) -> None:
        """Update the executing spinner and elapsed time."""
        if self._spinner and self._status_widget:
            frame = self._spinner.next_frame()
            elapsed = int(time() - self._executing_start_time)
            self._status_widget.update(f"{frame} working... ({elapsed}s)")

    def _stop_executing(self) -> None:
        """Stop the executing indicator."""
        if self._executing_timer is not None:
            self._executing_timer.stop()
            self._executing_timer = None
        if self._status_widget:
            self._status_widget.remove_class("executing")
            self._status_widget.display = False

    def set_success(self, result: str = "") -> None:
        """Mark the tool call as successful.

        Args:
            result: Tool output/result to display
        """
        self._stop_executing()
        self._status = "success"
        self._output = result
        # No status label for success - just show output
        self._update_output_display()

    def set_error(self, error: str) -> None:
        """Mark the tool call as failed.

        Args:
            error: Error message
        """
        self._stop_executing()
        self._status = "error"
        self._output = error
        if self._status_widget:
            self._status_widget.add_class("error")
            self._status_widget.update(f"[{_ERROR}]error[/{_ERROR}]")
            self._status_widget.display = True
        # Always show full error - errors should be visible
        self._expanded = True
        self._update_output_display()

    def set_rejected(self) -> None:
        """Mark the tool call as rejected by user."""
        self._stop_executing()
        self._status = "rejected"
        if self._status_widget:
            self._status_widget.add_class("rejected")
            self._status_widget.update(f"[{_TEXT_HINT}]rejected[/{_TEXT_HINT}]")
            self._status_widget.display = True

    def set_skipped(self) -> None:
        """Mark the tool call as skipped (due to another rejection)."""
        self._stop_executing()
        self._status = "skipped"
        if self._status_widget:
            self._status_widget.add_class("rejected")  # Use same styling as rejected
            self._status_widget.update(f"[{_TEXT_MUTED}]skipped[/{_TEXT_MUTED}]")
            self._status_widget.display = True

    def toggle_output(self) -> None:
        """Toggle between preview and full output display."""
        if not self._output:
            return
        self._expanded = not self._expanded
        self._update_output_display()

    def on_click(self) -> None:
        """Handle click to toggle output expansion."""
        self.toggle_output()

    def _update_output_display(self) -> None:
        """Update the output display based on expanded state."""
        if not self._output or not self._preview_widget:
            return

        output_stripped = self._output.strip()
        lines = output_stripped.split("\n")
        total_lines = len(lines)
        total_chars = len(output_stripped)

        # Truncate if too many lines OR too many characters
        needs_truncation = total_lines > self._PREVIEW_LINES or total_chars > self._PREVIEW_CHARS

        if self._expanded:
            # Show full output
            self._preview_widget.display = False
            self._hint_widget.display = False
            self._full_widget.update(self._output)
            self._full_widget.display = True
        else:
            # Show preview
            self._full_widget.display = False
            if needs_truncation:
                # Truncate by lines first, then by chars
                if total_lines > self._PREVIEW_LINES:
                    preview_text = "\n".join(lines[: self._PREVIEW_LINES])
                else:
                    preview_text = output_stripped

                # Also truncate by chars if still too long
                if len(preview_text) > self._PREVIEW_CHARS:
                    preview_text = preview_text[: self._PREVIEW_CHARS] + "..."

                self._preview_widget.update(preview_text)
                self._preview_widget.display = True

                # Show expand hint
                self._hint_widget.update("[dim]... (click or ctrl+o to expand)[/dim]")
                self._hint_widget.display = True
            elif output_stripped:
                # Output fits in preview, just show it
                self._preview_widget.update(output_stripped)
                self._preview_widget.display = True
                self._hint_widget.display = False
            else:
                self._preview_widget.display = False
                self._hint_widget.display = False

    @property
    def has_output(self) -> bool:
        """Check if this tool message has output to display."""
        return bool(self._output)

    def _filtered_args(self) -> dict[str, Any]:
        """Filter large tool args for display."""
        if self._tool_name not in {"write_file", "edit_file"}:
            return self._args

        filtered: dict[str, Any] = {}
        for key in ("file_path", "path", "replace_all"):
            if key in self._args:
                filtered[key] = self._args[key]
        return filtered


class DiffMessage(Static):
    """Widget displaying a diff with syntax highlighting."""

    DEFAULT_CSS = """
    DiffMessage {
        height: auto;
        padding: 1;
        margin: 1 0;
    }

    DiffMessage .diff-header {
        margin-bottom: 1;
    }

    DiffMessage .diff-add {
        color: #72d69f;
    }

    DiffMessage .diff-remove {
        color: #ff7a7a;
    }

    DiffMessage .diff-context {
        color: #9aa8b7;
    }

    DiffMessage .diff-hunk {
        color: #d0dbe7;
    }
    """

    def __init__(self, diff_content: str, file_path: str = "", **kwargs: Any) -> None:
        """Initialize a diff message.

        Args:
            diff_content: The unified diff content
            file_path: Path to the file being modified
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._diff_content = diff_content
        self._file_path = file_path

    def compose(self) -> ComposeResult:
        """Compose the diff message layout."""
        if self._file_path:
            yield Static(f"[bold]File: {self._file_path}[/bold]", classes="diff-header")

        # Render the diff with enhanced formatting
        rendered = format_diff_textual(self._diff_content, max_lines=100)
        yield Static(rendered)


class ErrorMessage(Static):
    """Widget displaying an error message."""

    DEFAULT_CSS = """
    ErrorMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    """

    def __init__(self, error: str, **kwargs: Any) -> None:
        """Initialize an error message.

        Args:
            error: The error message
            **kwargs: Additional arguments passed to parent
        """
        # Use Text object to combine styled prefix with unstyled error content
        text = Text("error ", style=_ERROR)
        text.append(error, style=_ERROR)
        super().__init__(text, **kwargs)


class SystemMessage(Static):
    """Widget displaying a system message."""

    DEFAULT_CSS = """
    SystemMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
        color: #9aa8b7;
    }
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialize a system message.

        Args:
            message: The system message
            **kwargs: Additional arguments passed to parent
        """
        # Use Text object to safely render message without markup parsing
        super().__init__(Text(message, style=_TEXT_MUTED), **kwargs)
