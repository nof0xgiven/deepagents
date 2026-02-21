"""Subagent streaming panel widget."""

from __future__ import annotations

from time import time
from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Markdown, Static
from textual.widgets._markdown import MarkdownStream

from deepagents_cli import theme
from deepagents_cli.widgets.loading import BrailleSpinner

if TYPE_CHECKING:
    from textual.app import ComposeResult


class SubagentPanel(Vertical):
    """Live panel showing streaming output for a single subagent namespace."""

    DEFAULT_CSS = """
    SubagentPanel {
        height: auto;
        max-height: 16;
        margin: 1 0;
        padding: 1 2;
        background: #0f161d 82%;
        border-left: thick #8cd8ff;
        border-right: solid #a7b4c2 28%;
        border-top: solid #a7b4c2 28%;
        border-bottom: solid #a7b4c2 28%;
        overflow-y: auto;
    }

    SubagentPanel .subagent-header-row {
        height: 1;
        width: 100%;
    }

    SubagentPanel .subagent-header {
        color: #dbe7f2;
        text-style: bold;
    }

    SubagentPanel .subagent-events {
        margin-top: 1;
        color: #9fb0c1;
    }
    """

    def __init__(
        self,
        namespace: tuple[str, ...],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.namespace = namespace
        self._label = namespace[-1] if namespace else "main"
        self._start_time = time()
        self._active = True
        self._spinner = BrailleSpinner()
        self._header_widget: Static | None = None
        self._markdown_widget: Markdown | None = None
        self._events_widget: Static | None = None
        self._header_timer: Timer | None = None
        self._stream: MarkdownStream | None = None
        self._content = ""
        self._events: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(classes="subagent-header-row"):
            yield Static("", classes="subagent-header", id="subagent-header")
        yield Markdown("", id="subagent-body")
        yield Static("", classes="subagent-events", id="subagent-events")

    def on_mount(self) -> None:
        self._header_widget = self.query_one("#subagent-header", Static)
        self._markdown_widget = self.query_one("#subagent-body", Markdown)
        self._events_widget = self.query_one("#subagent-events", Static)
        self._header_timer = self.set_interval(0.1, self._update_header)
        self._update_header()

    def on_unmount(self) -> None:
        if self._header_timer is not None:
            self._header_timer.stop()
            self._header_timer = None

    def _update_header(self) -> None:
        if self._header_widget is None:
            return
        elapsed = int(time() - self._start_time)
        if self._active:
            frame = self._spinner.next_frame()
            status = f"[{theme.ACCENT_DIM}]{frame} running[/{theme.ACCENT_DIM}]"
        else:
            status = f"[{theme.SUCCESS}]done[/{theme.SUCCESS}]"
        self._header_widget.update(
            f"[{theme.ACCENT}]subagent[/{theme.ACCENT}] "
            f"[{theme.PRIMARY}]{self._label}[/{theme.PRIMARY}] "
            f"({elapsed}s) · {status}"
        )

    def _ensure_stream(self) -> MarkdownStream:
        if self._stream is None:
            if self._markdown_widget is None:
                self._markdown_widget = self.query_one("#subagent-body", Markdown)
            self._stream = Markdown.get_stream(self._markdown_widget)
        return self._stream

    async def append_text(self, text: str) -> None:
        """Append streamed markdown text."""
        if not text:
            return
        self._content += text
        stream = self._ensure_stream()
        await stream.write(text)

    def append_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Append a compact tool-call event line."""
        if not tool_name:
            return
        keys = ", ".join(list(args.keys())[:3]) if args else "no args"
        suffix = "..." if args and len(args) > 3 else ""
        self.append_event(f"tool: {tool_name} ({keys}{suffix})")

    def append_event(self, line: str) -> None:
        """Append a compact status/event line."""
        if not line or self._events_widget is None:
            return
        self._events.append(line)
        self._events = self._events[-6:]
        self._events_widget.update("\n".join(f"• {item}" for item in self._events))

    async def complete(self) -> None:
        """Finalize stream state when subagent finishes."""
        self._active = False
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None
        self._update_header()
