"""Autocomplete system for / commands and @ file mentions.

Provides slash-command completion and fuzzy file completion triggered by @.
"""

from __future__ import annotations

import subprocess
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from textual import events


# ---------------------------------------------------------------------------
# Result enum
# ---------------------------------------------------------------------------


class CompletionResult(StrEnum):
    """Result of handling a key event in the completion system."""

    IGNORED = "ignored"  # Key not handled, let default behavior proceed
    HANDLED = "handled"  # Key handled, prevent default
    SUBMIT = "submit"  # Key triggers submission


# ---------------------------------------------------------------------------
# Protocols (kept for type-checking only)
# ---------------------------------------------------------------------------


class CompletionView(Protocol):
    """View that can display completion suggestions."""

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None: ...

    def clear_completion_suggestions(self) -> None: ...

    def replace_completion_range(self, start: int, end: int, replacement: str) -> None: ...


class CompletionController(Protocol):
    """Controller that provides completions."""

    def can_handle(self, text: str, cursor_index: int) -> bool: ...
    def on_text_changed(self, text: str, cursor_index: int) -> None: ...
    def on_key(self, event: events.Key, text: str, cursor_index: int) -> CompletionResult: ...
    def reset(self) -> None: ...


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/assemble", "Assemble Linear issue workflow"),
    ("/model", "Select or switch the active model"),
    ("/debug", "Debug model resolution and settings"),
    ("/help", "Show help"),
    ("/clear", "Clear chat and start new session"),
    ("/remember", "Update memory and skills from conversation"),
    ("/quit", "Exit app"),
    ("/exit", "Exit app"),
    ("/tokens", "Token usage"),
    ("/threads", "Show session info"),
    ("/version", "Show version"),
]
"""Built-in slash commands with descriptions."""

MAX_SUGGESTIONS = 10


# ---------------------------------------------------------------------------
# SlashCommandController
# ---------------------------------------------------------------------------


class SlashCommandController:
    """Completion controller for ``/`` slash commands.

    Retained for compatibility; ChatInput now owns slash-command UX.
    """

    def __init__(self, commands: list[tuple[str, str]], view: CompletionView) -> None:
        self._commands = commands
        self._view = view
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0

    def can_handle(self, text: str, cursor_index: int) -> bool:  # noqa: ARG002
        """Active when the *entire* text is a (partial) slash command.

        Returns ``False`` once a space appears after the command name, since
        at that point the user is typing arguments, not the command itself.
        """
        if not text.startswith("/"):
            return False
        # If there's a space the command part is over
        return " " not in text

    def reset(self) -> None:
        """Clear suggestions."""
        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Update suggestions when text changes."""
        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        search = text[1:cursor_index].lower()

        suggestions = [
            (cmd, desc)
            for cmd, desc in self._commands
            if cmd.lower().startswith("/" + search)
        ][:MAX_SUGGESTIONS]

        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            self._view.render_completion_suggestions(self._suggestions, self._selected_index)
        else:
            self.reset()

    def on_key(self, event: events.Key, _text: str, cursor_index: int) -> CompletionResult:
        """Handle key events for navigation and selection."""
        if not self._suggestions:
            return CompletionResult.IGNORED

        key = event.key
        if key == "tab":
            self._apply_selected(cursor_index)
            return CompletionResult.HANDLED
        if key == "enter":
            self._apply_selected(cursor_index)
            return CompletionResult.SUBMIT
        if key == "down":
            self._move_selection(1)
            return CompletionResult.HANDLED
        if key == "up":
            self._move_selection(-1)
            return CompletionResult.HANDLED
        if key == "escape":
            self.reset()
            return CompletionResult.HANDLED
        return CompletionResult.IGNORED

    def _move_selection(self, delta: int) -> None:
        """Move selection up or down."""
        if not self._suggestions:
            return
        self._selected_index = (self._selected_index + delta) % len(self._suggestions)
        self._view.render_completion_suggestions(self._suggestions, self._selected_index)

    def _apply_selected(self, cursor_index: int) -> None:
        """Apply the currently selected completion."""
        if not self._suggestions:
            return
        command, _ = self._suggestions[self._selected_index]
        self._view.replace_completion_range(0, cursor_index, command)
        self.reset()


# ---------------------------------------------------------------------------
# Fuzzy file completion helpers
# ---------------------------------------------------------------------------

_MAX_FALLBACK_FILES = 1000
_MIN_FUZZY_RATIO = 0.4
_MIN_FUZZY_SCORE = 15  # Minimum score to include in results


def _find_project_root(start_path: Path) -> Path:
    """Walk up to find the nearest ``.git`` directory."""
    current = start_path.resolve()
    for parent in [current, *list(current.parents)]:
        if (parent / ".git").exists():
            return parent
    return start_path


def _get_project_files(root: Path) -> list[str]:
    """List files via ``git ls-files`` with a glob fallback."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")
            return [f for f in files if f]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: limited-depth glob
    files: list[str] = []
    try:
        for pattern in ["*", "*/*", "*/*/*", "*/*/*/*"]:
            for p in root.glob(pattern):
                if p.is_file() and not any(part.startswith(".") for part in p.parts):
                    files.append(str(p.relative_to(root)))
                if len(files) >= _MAX_FALLBACK_FILES:
                    break
            if len(files) >= _MAX_FALLBACK_FILES:
                break
    except OSError:
        pass
    return files


def _fuzzy_score(query: str, candidate: str) -> float:  # noqa: PLR0911
    """Score *candidate* against *query*. Higher is better."""
    query_lower = query.lower()
    candidate_lower = candidate.lower()

    filename = candidate.rsplit("/", 1)[-1].lower()
    filename_start = candidate_lower.rfind("/") + 1

    # --- filename substring matches (highest priority) ---
    if query_lower in filename:
        idx = filename.find(query_lower)
        if idx == 0:
            return 150 + (1 / len(candidate))
        if idx > 0 and filename[idx - 1] in "_-.":
            return 120 + (1 / len(candidate))
        return 100 + (1 / len(candidate))

    # --- full-path substring matches ---
    if query_lower in candidate_lower:
        idx = candidate_lower.find(query_lower)
        if idx == filename_start:
            return 80 + (1 / len(candidate))
        if idx == 0 or candidate[idx - 1] in "/_-.":
            return 60 + (1 / len(candidate))
        return 40 + (1 / len(candidate))

    # --- fuzzy on filename ---
    filename_ratio = SequenceMatcher(None, query_lower, filename).ratio()
    if filename_ratio > _MIN_FUZZY_RATIO:
        return filename_ratio * 30

    # --- fuzzy on full path ---
    return SequenceMatcher(None, query_lower, candidate_lower).ratio() * 15


def _is_dotpath(path: str) -> bool:
    """Check if path contains dotfiles/dotdirs (e.g., .github/...)."""
    return any(part.startswith(".") for part in path.split("/"))


def _path_depth(path: str) -> int:
    """Get depth of path (number of ``/`` separators)."""
    return path.count("/")


def _fuzzy_search(
    query: str,
    candidates: list[str],
    limit: int = 10,
    *,
    include_dotfiles: bool = False,
) -> list[str]:
    """Return top *limit* matches sorted by score."""
    filtered = candidates if include_dotfiles else [c for c in candidates if not _is_dotpath(c)]

    if not query:
        sorted_files = sorted(filtered, key=lambda p: (_path_depth(p), p.lower()))
        return sorted_files[:limit]

    scored = [
        (score, c)
        for c in filtered
        if (score := _fuzzy_score(query, c)) >= _MIN_FUZZY_SCORE
    ]
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]


# ---------------------------------------------------------------------------
# FuzzyFileController
# ---------------------------------------------------------------------------


class FuzzyFileController:
    """Completion controller for ``@`` file mentions with fuzzy matching."""

    def __init__(self, view: CompletionView, cwd: Path | None = None) -> None:
        self._view = view
        self._cwd = cwd or Path.cwd()
        self._project_root = _find_project_root(self._cwd)
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0
        self._file_cache: list[str] | None = None

    def can_handle(self, text: str, cursor_index: int) -> bool:
        """Active when there is an ``@`` before the cursor with no spaces after it."""
        if cursor_index <= 0 or cursor_index > len(text):
            return False
        before_cursor = text[:cursor_index]
        if "@" not in before_cursor:
            return False
        at_index = before_cursor.rfind("@")
        if cursor_index <= at_index:
            return False
        fragment = before_cursor[at_index:cursor_index]
        return bool(fragment) and " " not in fragment

    def reset(self) -> None:
        """Clear suggestions."""
        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    def refresh_cache(self) -> None:
        """Force-refresh the cached file list."""
        self._file_cache = None

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Update suggestions when text changes."""
        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        before_cursor = text[:cursor_index]
        at_index = before_cursor.rfind("@")
        search = before_cursor[at_index + 1 :]

        suggestions = self._get_fuzzy_suggestions(search)

        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            self._view.render_completion_suggestions(self._suggestions, self._selected_index)
        else:
            self.reset()

    def on_key(self, event: events.Key, text: str, cursor_index: int) -> CompletionResult:
        """Handle key events for navigation and selection."""
        if not self._suggestions:
            return CompletionResult.IGNORED

        key = event.key
        if key in ("tab", "enter"):
            if self._apply_selected(text, cursor_index):
                return CompletionResult.HANDLED
            return CompletionResult.IGNORED
        if key == "down":
            self._move_selection(1)
            return CompletionResult.HANDLED
        if key == "up":
            self._move_selection(-1)
            return CompletionResult.HANDLED
        if key == "escape":
            self.reset()
            return CompletionResult.HANDLED
        return CompletionResult.IGNORED

    # -- private helpers -----------------------------------------------------

    def _get_files(self) -> list[str]:
        """Get cached file list or refresh."""
        if self._file_cache is None:
            self._file_cache = _get_project_files(self._project_root)
        return self._file_cache

    def _get_fuzzy_suggestions(self, search: str) -> list[tuple[str, str]]:
        """Get fuzzy file suggestions."""
        files = self._get_files()
        include_dots = search.startswith(".")
        matches = _fuzzy_search(search, files, limit=MAX_SUGGESTIONS, include_dotfiles=include_dots)

        suggestions: list[tuple[str, str]] = []
        for path in matches:
            ext = Path(path).suffix.lower()
            type_hint = ext[1:] if ext else "file"
            suggestions.append((f"@{path}", type_hint))
        return suggestions

    def _move_selection(self, delta: int) -> None:
        """Move selection up or down."""
        if not self._suggestions:
            return
        self._selected_index = (self._selected_index + delta) % len(self._suggestions)
        self._view.render_completion_suggestions(self._suggestions, self._selected_index)

    def _apply_selected(self, text: str, cursor_index: int) -> bool:
        """Apply the currently selected completion."""
        if not self._suggestions:
            return False
        label, _ = self._suggestions[self._selected_index]
        before_cursor = text[:cursor_index]
        at_index = before_cursor.rfind("@")
        if at_index < 0:
            return False
        self._view.replace_completion_range(at_index, cursor_index, label)
        self.reset()
        return True


# Backwards-compat alias
PathCompletionController = FuzzyFileController


# ---------------------------------------------------------------------------
# MultiCompletionManager
# ---------------------------------------------------------------------------


class MultiCompletionManager:
    """Delegates to the first matching controller from an ordered list."""

    def __init__(self, controllers: list[CompletionController]) -> None:
        self._controllers = controllers
        self._active: CompletionController | None = None

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        """Activate the first controller that can handle the current input."""
        candidate = None
        for ctrl in self._controllers:
            if ctrl.can_handle(text, cursor_index):
                candidate = ctrl
                break

        if candidate is None:
            if self._active is not None:
                self._active.reset()
                self._active = None
            return

        if candidate is not self._active:
            if self._active is not None:
                self._active.reset()
            self._active = candidate

        candidate.on_text_changed(text, cursor_index)

    def on_key(self, event: events.Key, text: str, cursor_index: int) -> CompletionResult:
        """Delegate key event to the active controller."""
        if self._active is None:
            return CompletionResult.IGNORED
        return self._active.on_key(event, text, cursor_index)

    def reset(self) -> None:
        """Reset all controllers."""
        if self._active is not None:
            self._active.reset()
            self._active = None
