"""Chat input widget for deepagents-cli with autocomplete and history support.

Key handling architecture
-------------------------
Textual delivers key events to the *focused* widget first, then bubbles them
up the DOM.  ``ChatTextArea`` (the focused widget) therefore sees every key
before ``ChatInput`` (its parent container).

To avoid race-conditions between the two handlers the responsibilities are
split cleanly:

* **ChatTextArea._on_key** – handles *only* newline-insertion shortcuts
  (shift+enter, ctrl+j …).  For ``enter``, ``tab``, ``up``, ``down`` and
  ``escape`` it calls ``event.prevent_default()`` so the base ``TextArea``
  doesn't act on them, but does **not** call ``event.stop()`` so the event
  keeps bubbling.  Everything else is forwarded to ``super()._on_key``.

* **ChatInput.on_key** – the single brain that routes every bubbled key:
  slash-menu first, then completion-manager, then submission / history.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from rich.markup import escape
from rich.text import Text

from textual import events  # noqa: TC002 - used at runtime in _on_key
from textual.binding import Binding
from textual.color import Color
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, TextArea

from deepagents_cli import theme
from deepagents_cli.widgets.autocomplete import (
    SLASH_COMMANDS,
    CompletionResult,
    FuzzyFileController,
    MultiCompletionManager,
)
from deepagents_cli.widgets.history import HistoryManager

if TYPE_CHECKING:
    from textual.app import ComposeResult


# ---------------------------------------------------------------------------
# Completion popup
# ---------------------------------------------------------------------------


class CompletionPopup(Static):
    """Popup widget that displays completion suggestions."""

    DEFAULT_CSS = """
    CompletionPopup {
        display: none;
        dock: top;
        layer: autocomplete;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the completion popup."""
        super().__init__("", **kwargs)
        self.can_focus = False

    def update_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        """Update the popup with new suggestions."""
        if not suggestions:
            self.hide()
            return

        # Build clean, scan-friendly list for dense completion sets.
        lines = []
        for idx, (label, description) in enumerate(suggestions):
            is_selected = idx == selected_index

            if is_selected:
                line = Text()
                line.append("> ", style="#33bfff bold")
                line.append(label, style="bold #eef4fb")
                if description:
                    line.append("  " + description, style="#b6c4d2")
            else:
                line = Text()
                line.append("  ")
                line.append(label, style="#d3dee9")
                if description:
                    line.append("  " + description, style="#91a1b1")

            lines.append(line)

        result = Text("\n").join(lines)
        self.update(result)
        self.show()

    def hide(self) -> None:
        """Hide the popup."""
        self.update("")
        self.styles.display = "none"

    def show(self) -> None:
        """Show the popup."""
        self.styles.display = "block"


# ---------------------------------------------------------------------------
# Slash command menu
# ---------------------------------------------------------------------------


class SlashCommandRow(Static):
    """Single row in the slash command menu."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", classes="slash-command-row", **kwargs)
        self.can_focus = False
        self.hide_row()

    def set_content(self, label: str, description: str) -> None:
        if description:
            padded = escape(label).ljust(20)
            self.update(f"{padded} [#9fb0c0]{escape(description)}[/#9fb0c0]")
        else:
            self.update(escape(label))

    def set_selected(self, selected: bool) -> None:
        self.set_class(selected, "selected")

    def hide_row(self) -> None:
        self.update("")
        self.styles.display = "none"

    def show_row(self) -> None:
        self.styles.display = "block"


class SlashCommandMenu(VerticalScroll):
    """Dedicated slash command suggestion menu with internal scrolling."""

    def __init__(self, max_rows: int = 12, **kwargs: Any) -> None:
        super().__init__(classes="slash-command-menu", **kwargs)
        self.can_focus = False
        self._max_rows = max_rows
        self._rows: list[SlashCommandRow] = []

    def compose(self) -> ComposeResult:
        for _ in range(self._max_rows):
            yield SlashCommandRow()

    def on_mount(self) -> None:
        self._rows = list(self.query(SlashCommandRow))
        self.hide_menu()

    def update_suggestions(
        self,
        suggestions: list[tuple[str, str]],
        selected_index: int,
    ) -> None:
        visible_rows = min(len(suggestions), len(self._rows))

        for index, row in enumerate(self._rows):
            if index < visible_rows:
                label, description = suggestions[index]
                row.set_content(label, description)
                row.set_selected(index == selected_index)
                row.show_row()
            else:
                row.set_selected(False)
                row.hide_row()

        if visible_rows > 0:
            self.show_menu()
            # Scroll selected row into view
            if 0 <= selected_index < visible_rows:
                self._rows[selected_index].scroll_visible(animate=False)
        else:
            self.hide_menu()

    def hide_menu(self) -> None:
        self.styles.display = "none"

    def show_menu(self) -> None:
        self.styles.display = "block"


# ---------------------------------------------------------------------------
# ChatTextArea – a "dumb" TextArea that only owns newline insertion
# ---------------------------------------------------------------------------

# Keys that must NOT be processed by the base TextArea (they are handled by
# ChatInput after bubbling).  We call prevent_default() but NOT stop() so
# they continue to propagate up the DOM.
_PASSTHROUGH_KEYS = frozenset({"enter", "tab", "up", "down", "escape"})


class ChatTextArea(TextArea):
    """TextArea subclass with custom key handling for chat input.

    This widget is intentionally kept simple.  It only intercepts newline-
    insertion combos.  All other "special" keys (enter for submit, tab for
    completion, up/down for history or completion navigation, escape) are
    blocked from the base ``TextArea`` via ``prevent_default()`` and left to
    bubble up to ``ChatInput.on_key``.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(
            "shift+enter,ctrl+j,alt+enter,ctrl+enter",
            "insert_newline",
            "New Line",
            show=False,
            priority=True,
        ),
        Binding(
            "ctrl+a",
            "select_all_text",
            "Select All",
            show=False,
            priority=True,
        ),
        Binding("cmd+z,super+z", "undo", "Undo", show=False, priority=True),
        Binding("cmd+shift+z,super+shift+z", "redo", "Redo", show=False, priority=True),
    ]

    # -- Messages ------------------------------------------------------------

    class Submitted(Message):
        """Message sent when text is submitted."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class HistoryPrevious(Message):
        """Request previous history entry."""

        def __init__(self, current_text: str) -> None:
            self.current_text = current_text
            super().__init__()

    class HistoryNext(Message):
        """Request next history entry."""

    # -- Lifecycle -----------------------------------------------------------

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("placeholder", None)
        super().__init__(**kwargs)
        self._navigating_history = False
        self._app_has_focus = True

    # -- Public helpers ------------------------------------------------------

    def set_app_focus(self, *, has_focus: bool) -> None:
        self._app_has_focus = has_focus
        self.cursor_blink = has_focus
        if has_focus and not self.has_focus:
            self.call_after_refresh(self.focus)

    def set_text_from_history(self, text: str) -> None:
        self._navigating_history = True
        self.text = text
        lines = text.split("\n")
        last_row = len(lines) - 1
        last_col = len(lines[last_row])
        self.move_cursor((last_row, last_col))
        self._navigating_history = False

    def clear_text(self) -> None:
        self.text = ""
        self.move_cursor((0, 0))

    # -- Actions (bound via BINDINGS) ----------------------------------------

    def action_insert_newline(self) -> None:
        self.insert("\n")

    def action_select_all_text(self) -> None:
        if not self.text:
            return
        lines = self.text.split("\n")
        end_row = len(lines) - 1
        end_col = len(lines[end_row])
        self.selection = ((0, 0), (end_row, end_col))

    # -- Key handling --------------------------------------------------------

    async def _on_key(self, event: events.Key) -> None:
        # Newline insertion – fully handled here, stop propagation.
        if event.key in ("shift+enter", "ctrl+j", "alt+enter", "ctrl+enter"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        # Keys that ChatInput needs to handle: block the base TextArea's
        # default behaviour but let the event bubble upward.
        if event.key in _PASSTHROUGH_KEYS:
            event.prevent_default()
            # NOTE: we intentionally do NOT call event.stop() here.
            return

        # Everything else (regular characters, backspace, arrows that aren't
        # at the boundary, etc.) – delegate to the normal TextArea handler.
        await super()._on_key(event)


# ---------------------------------------------------------------------------
# ChatInput – the main container and the single "brain" for completions,
# submission and history navigation.
# ---------------------------------------------------------------------------


class ChatInput(Vertical):
    """Chat input widget with autocomplete – popup floats above."""

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 4;
        max-height: 16;
        padding: 1 2;
        background: transparent;
        border: solid #a7b4c2 42%;
    }

    ChatInput .input-row {
        height: auto;
        width: 100%;
    }

    ChatInput .input-prompt {
        width: 2;
        height: 1;
        padding: 0;
        color: #8898a8;
    }

    ChatInput ChatTextArea {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 6;
        border: none;
        background: transparent;
        padding: 0;
        color: #f4f8fc;
    }

    ChatInput ChatTextArea:focus {
        border: none;
    }

    """

    # -- Messages ------------------------------------------------------------

    class Submitted(Message):
        def __init__(self, value: str, mode: str = "normal") -> None:
            super().__init__()
            self.value = value
            self.mode = mode

    class ModeChanged(Message):
        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

    class SlashMenuUpdate(Message):
        """Emitted when slash command suggestions change."""

        def __init__(
            self,
            suggestions: list[tuple[str, str]],
            selected_index: int,
            *,
            visible: bool,
        ) -> None:
            super().__init__()
            self.suggestions = suggestions
            self.selected_index = selected_index
            self.visible = visible

    # -- Reactives -----------------------------------------------------------

    mode: reactive[str] = reactive("normal")

    # -- Lifecycle -----------------------------------------------------------

    def __init__(
        self,
        cwd: str | Path | None = None,
        history_file: Path | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._cwd = Path(cwd) if cwd else Path.cwd()
        self._text_area: ChatTextArea | None = None
        self._popup: CompletionPopup | None = None
        self._completion_manager: MultiCompletionManager | None = None
        self._slash_visible = False
        self._slash_suggestions: list[tuple[str, str]] = []
        self._slash_selected_index = 0
        self._slash_query_start = 0
        self._slash_query_end = 0

        if history_file is None:
            history_file = Path.home() / ".deepagents" / "history.jsonl"
        self._history = HistoryManager(history_file)
        self._submit_enabled = True

    def compose(self) -> ComposeResult:
        """Compose layout – popup first so it stacks above input."""
        yield CompletionPopup(id="completion-popup")
        with Horizontal(classes="input-row"):
            yield Static("\u276f", classes="input-prompt", id="prompt")
            yield ChatTextArea(id="chat-input")

    def on_mount(self) -> None:
        self._text_area = self.query_one("#chat-input", ChatTextArea)
        self._popup = self.query_one("#completion-popup", CompletionPopup)

        self._completion_manager = MultiCompletionManager(
            [
                FuzzyFileController(self, cwd=self._cwd),
            ]
        )

        self._text_area.focus()

    # -- Text changes → completion manager -----------------------------------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        cursor_offset = self._get_cursor_offset()

        stripped = text.lstrip()

        # Detect mode from leading command marker (ignoring incidental indentation).
        if stripped.startswith("!"):
            self.mode = "bash"
        elif stripped.startswith("/"):
            self.mode = "command"
        else:
            self.mode = "normal"

        # Don't trigger completion while navigating history.
        if self._text_area and self._text_area._navigating_history:
            self._clear_slash_menu()
            if self._completion_manager:
                self._completion_manager.reset()
            return

        self._update_slash_suggestions(text, cursor_offset)
        if self._slash_visible:
            if self._completion_manager:
                self._completion_manager.reset()
            return

        if self._completion_manager and self._text_area:
            self._completion_manager.on_text_changed(text, cursor_offset)

    # -- Key routing (the SINGLE brain) --------------------------------------

    async def on_key(self, event: events.Key) -> None:  # noqa: PLR0912
        """Central key router.

        By the time we get here, ChatTextArea has already called
        ``prevent_default()`` for enter/tab/up/down/escape (so the base
        TextArea won't act on them) but has *not* stopped propagation.

        We now decide what to do with the key:

        1. Ask the slash menu – if it handles the key we're done.
        2. Ask the completion manager (@) – if it handles we're done.
        3. If still ignored, fall through to enter submit / history navigation.
        """
        if not self._text_area:
            return

        text = self._text_area.text
        cursor = self._get_cursor_offset()

        # --- 1. Slash menu gets first shot ---------------------------------
        slash_result = self._handle_slash_menu_key(event)
        if slash_result is CompletionResult.HANDLED:
            event.stop()
            return
        if slash_result is CompletionResult.SUBMIT:
            event.stop()
            self._do_submit(mode_override="command")
            return

        # --- 2. Completion manager gets second shot ------------------------
        if self._completion_manager:
            result = self._completion_manager.on_key(event, text, cursor)

            if result is CompletionResult.HANDLED:
                event.stop()
                return

            if result is CompletionResult.SUBMIT:
                event.stop()
                self._do_submit()
                return

        # --- 3. Fallback handling for keys that ChatTextArea passed through --

        if event.key == "enter":
            event.stop()
            self._do_submit()
            return

        if event.key == "up":
            row, _ = self._text_area.cursor_location
            if row == 0:
                event.stop()
                self._text_area._navigating_history = True
                self._text_area.post_message(
                    ChatTextArea.HistoryPrevious(self._text_area.text),
                )
            return

        if event.key == "down":
            row, _ = self._text_area.cursor_location
            total_lines = self._text_area.text.count("\n") + 1
            if row == total_lines - 1:
                event.stop()
                self._text_area._navigating_history = True
                self._text_area.post_message(ChatTextArea.HistoryNext())
            return

        if event.key == "escape":
            # Escape with no active completion – nothing to do (let it bubble
            # for any app-level binding).
            return

        if event.key == "tab":
            # Tab with no active completion – ignore (don't insert a tab).
            event.stop()
            return

    # -- Submit helper -------------------------------------------------------

    def _do_submit(self, mode_override: str | None = None) -> None:
        """Submit the current text if non-empty and submission is enabled."""
        if not self._text_area or not self._submit_enabled:
            return

        value = self._text_area.text.strip()
        if not value:
            return

        if self._completion_manager:
            self._completion_manager.reset()
        self._clear_slash_menu()

        self._history.add(value)
        submit_mode = mode_override if mode_override is not None else self.mode
        self.post_message(self.Submitted(value, submit_mode))
        self._text_area.clear_text()
        self.mode = "normal"

    # -- History messages (bubbled from ChatTextArea) -------------------------

    def on_chat_text_area_history_previous(
        self, event: ChatTextArea.HistoryPrevious
    ) -> None:
        entry = self._history.get_previous(event.current_text)
        if entry is not None and self._text_area:
            self._text_area.set_text_from_history(entry)

    def on_chat_text_area_history_next(
        self,
        event: ChatTextArea.HistoryNext,  # noqa: ARG002
    ) -> None:
        entry = self._history.get_next()
        if entry is not None and self._text_area:
            self._text_area.set_text_from_history(entry)

    # -- Cursor-offset helper ------------------------------------------------

    def _get_cursor_offset(self) -> int:
        if not self._text_area:
            return 0

        text = self._text_area.text
        row, col = self._text_area.cursor_location

        if not text:
            return 0

        lines = text.split("\n")
        row = max(0, min(row, len(lines) - 1))
        col = max(0, col)

        offset = sum(len(lines[i]) + 1 for i in range(row))
        return offset + min(col, len(lines[row]))

    # -- Reactive watchers ---------------------------------------------------

    def watch_mode(self, mode: str) -> None:
        self._update_prompt_symbol()
        self.post_message(self.ModeChanged(mode))

    # -- Public API ----------------------------------------------------------

    def focus_input(self) -> None:
        if self._text_area:
            self._text_area.focus()

    @property
    def value(self) -> str:
        if self._text_area:
            return self._text_area.text
        return ""

    @value.setter
    def value(self, val: str) -> None:
        if self._text_area:
            self._text_area.text = val

    @property
    def input_widget(self) -> ChatTextArea | None:
        return self._text_area

    def set_disabled(self, *, disabled: bool) -> None:
        if self._text_area:
            self._text_area.disabled = disabled
            if disabled:
                self._text_area.blur()
                self._clear_slash_menu()
                if self._completion_manager:
                    self._completion_manager.reset()

    def set_submit_enabled(self, *, enabled: bool) -> None:
        self._submit_enabled = enabled

    def set_cursor_active(self, *, active: bool) -> None:
        if self._text_area:
            self._text_area.set_app_focus(has_focus=active)

    def set_prompt_active(self, *, active: bool) -> None:
        try:
            prompt = self.query_one("#prompt", Static)
        except Exception:
            return
        self._update_prompt_symbol(prompt)
        if active:
            border_color = Color.parse(theme.ACCENT).with_alpha(0.55)
            self.styles.border = ("solid", border_color)
            # Set prompt color based on mode
            if self.mode == "bash":
                prompt.styles.color = theme.WARNING
            elif self.mode == "command":
                prompt.styles.color = theme.ACCENT_DIM
            else:
                prompt.styles.color = theme.ACCENT_DIM
        else:
            border_color = Color.parse(theme.BORDER_DIM).with_alpha(0.25)
            self.styles.border = ("solid", border_color)
            prompt.styles.color = theme.HINT
            if self._text_area:
                self._text_area.cursor_blink = False

    def _update_prompt_symbol(self, prompt: Static | None = None) -> None:
        """Update prompt character based on current mode."""
        if prompt is None:
            try:
                prompt = self.query_one("#prompt", Static)
            except Exception:
                return
        if self.mode == "bash":
            prompt.update("!")
        elif self.mode == "command":
            prompt.update("/")
        else:
            prompt.update("\u276f")  # ❯

    # -- CompletionView protocol ---------------------------------------------

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        if self._popup:
            self._popup.update_suggestions(suggestions, selected_index)

    def clear_completion_suggestions(self) -> None:
        if self._popup:
            self._popup.hide()

    def replace_completion_range(self, start: int, end: int, replacement: str) -> None:
        self._replace_text_range(start, end, replacement, add_trailing_space=True)

    # -- Slash command menu internals ---------------------------------------

    def _handle_slash_menu_key(self, event: events.Key) -> CompletionResult:
        if not self._slash_visible or not self._slash_suggestions:
            return CompletionResult.IGNORED

        key = event.key
        if key == "down":
            self._move_slash_selection(1)
            return CompletionResult.HANDLED
        if key == "up":
            self._move_slash_selection(-1)
            return CompletionResult.HANDLED
        if key == "tab":
            if self._apply_selected_slash(add_trailing_space=True):
                return CompletionResult.HANDLED
            return CompletionResult.IGNORED
        if key == "enter":
            if self._apply_selected_slash(add_trailing_space=False):
                return CompletionResult.SUBMIT
            return CompletionResult.IGNORED
        if key == "escape":
            self._clear_slash_menu()
            return CompletionResult.HANDLED
        return CompletionResult.IGNORED

    def _move_slash_selection(self, delta: int) -> None:
        if not self._slash_suggestions:
            return
        self._slash_selected_index = (self._slash_selected_index + delta) % len(
            self._slash_suggestions
        )
        self._render_slash_menu()

    def _apply_selected_slash(self, *, add_trailing_space: bool) -> bool:
        if not self._slash_suggestions:
            return False
        command, _ = self._slash_suggestions[self._slash_selected_index]
        self._replace_text_range(
            self._slash_query_start,
            self._slash_query_end,
            command,
            add_trailing_space=add_trailing_space,
        )
        self._clear_slash_menu()
        return True

    def _update_slash_suggestions(self, text: str, cursor_offset: int) -> None:
        context = self._get_slash_query_context(text, cursor_offset)
        if context is None:
            self._clear_slash_menu()
            return

        start, end, query = context
        query_lower = query.lower()
        suggestions = [
            (command, description)
            for command, description in SLASH_COMMANDS
            if command.lower().startswith("/" + query_lower)
        ][:10]

        if not suggestions:
            self._clear_slash_menu()
            return

        if suggestions != self._slash_suggestions:
            self._slash_selected_index = 0
        else:
            self._slash_selected_index = min(
                self._slash_selected_index, len(suggestions) - 1
            )

        self._slash_suggestions = suggestions
        self._slash_query_start = start
        self._slash_query_end = end
        self._slash_visible = True
        self._render_slash_menu()

    def _get_slash_query_context(
        self, text: str, cursor_offset: int
    ) -> tuple[int, int, str] | None:
        if not text:
            return None

        cursor = max(0, min(cursor_offset, len(text)))
        first_non_ws = 0
        while first_non_ws < len(text) and text[first_non_ws].isspace():
            first_non_ws += 1

        if first_non_ws >= len(text) or text[first_non_ws] != "/":
            return None

        command_end = len(text)
        for index in range(first_non_ws, len(text)):
            if text[index].isspace():
                command_end = index
                break

        if cursor <= first_non_ws or cursor > command_end:
            return None

        query = text[first_non_ws + 1 : cursor]
        return first_non_ws, command_end, query

    def _render_slash_menu(self) -> None:
        if not self._slash_visible or not self._slash_suggestions:
            self.post_message(self.SlashMenuUpdate([], 0, visible=False))
            return
        self.post_message(
            self.SlashMenuUpdate(
                self._slash_suggestions, self._slash_selected_index, visible=True
            )
        )

    def _clear_slash_menu(self) -> None:
        self._slash_visible = False
        self._slash_suggestions = []
        self._slash_selected_index = 0
        self._slash_query_start = 0
        self._slash_query_end = 0
        self.post_message(self.SlashMenuUpdate([], 0, visible=False))

    # -- Text replacement helper -------------------------------------------

    def _replace_text_range(
        self,
        start: int,
        end: int,
        replacement: str,
        *,
        add_trailing_space: bool,
    ) -> None:
        if not self._text_area:
            return

        text = self._text_area.text
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))

        prefix = text[:start]
        suffix = text[end:]

        insertion = replacement
        if (
            add_trailing_space
            and not replacement.endswith("/")
            and not suffix.startswith(" ")
        ):
            insertion = replacement + " "

        new_text = f"{prefix}{insertion}{suffix}"
        self._text_area.text = new_text

        new_offset = start + len(insertion)
        lines = new_text.split("\n")
        remaining = new_offset
        for row, line in enumerate(lines):
            if remaining <= len(line):
                self._text_area.move_cursor((row, remaining))
                break
            remaining -= len(line) + 1
