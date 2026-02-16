"""Enhanced diff widget for displaying unified diffs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from textual.containers import Vertical
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


def _escape_markup(text: str) -> str:
    """Escape Rich markup characters in text.

    Args:
        text: Text that may contain Rich markup

    Returns:
        Escaped text safe for Rich rendering
    """
    # Escape brackets that could be interpreted as markup
    return text.replace("[", r"\[").replace("]", r"\]")


def format_diff_textual(diff: str, max_lines: int | None = 100) -> str:
    """Format a unified diff with line numbers and colors.

    Args:
        diff: Unified diff string
        max_lines: Maximum number of diff lines to show (None for unlimited)

    Returns:
        Rich-formatted diff string with line numbers
    """
    if not diff:
        return "[dim]No changes detected[/dim]"

    lines = diff.splitlines()

    # Compute stats first
    additions = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    deletions = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))

    # Find max line number for width calculation
    max_line = 0
    for line in lines:
        if m := re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line):
            max_line = max(max_line, int(m.group(1)), int(m.group(2)))
    width = max(3, len(str(max_line + len(lines))))

    formatted = []

    # Add stats header
    stats_parts = []
    if additions:
        stats_parts.append(f"[#72d69f]+{additions}[/#72d69f]")
    if deletions:
        stats_parts.append(f"[#ff7a7a]-{deletions}[/#ff7a7a]")
    if stats_parts:
        formatted.append(" ".join(stats_parts))
        formatted.append("")  # Blank line after stats

    old_num = new_num = 0
    line_count = 0

    for line in lines:
        if max_lines and line_count >= max_lines:
            formatted.append(f"\n[dim]... ({len(lines) - line_count} more lines)[/dim]")
            break

        # Skip file headers (--- and +++)
        if line.startswith(("---", "+++")):
            continue

        # Handle hunk headers - just update line numbers, don't display
        if m := re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line):
            old_num, new_num = int(m.group(1)), int(m.group(2))
            continue

        # Handle diff lines - use gutter bar instead of +/- prefix
        content = line[1:] if line else ""
        escaped_content = _escape_markup(content)

        if line.startswith("-"):
            formatted.append(
                f"[#94a5b6]{old_num:>{width}}[/#94a5b6] "
                f"[#ff7a7a]-{escaped_content}[/#ff7a7a]"
            )
            old_num += 1
            line_count += 1
        elif line.startswith("+"):
            formatted.append(
                f"[#94a5b6]{new_num:>{width}}[/#94a5b6] "
                f"[#72d69f]+{escaped_content}[/#72d69f]"
            )
            new_num += 1
            line_count += 1
        elif line.startswith(" "):
            formatted.append(f"[#94a5b6]{old_num:>{width}}[/#94a5b6]  {escaped_content}")
            old_num += 1
            new_num += 1
            line_count += 1
        elif line.strip() == "...":
            formatted.append("[#94a5b6]...[/#94a5b6]")
            line_count += 1

    return "\n".join(formatted)


class EnhancedDiff(Vertical):
    """Widget for displaying a unified diff with syntax highlighting."""

    DEFAULT_CSS = """
    EnhancedDiff {
        height: auto;
        padding: 1;
        background: transparent;
        border-left: solid #98a8b8 42%;
    }

    EnhancedDiff .diff-title {
        color: #d0dbe7;
        margin-bottom: 1;
    }

    EnhancedDiff .diff-content {
        height: auto;
    }

    EnhancedDiff .diff-stats {
        color: #b8c6d4;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        diff: str,
        title: str = "Diff",
        max_lines: int | None = 100,
        **kwargs: Any,
    ) -> None:
        """Initialize the diff widget.

        Args:
            diff: Unified diff string
            title: Title to display above the diff
            max_lines: Maximum number of diff lines to show
            **kwargs: Additional arguments passed to parent
        """
        super().__init__(**kwargs)
        self._diff = diff
        self._title = title
        self._max_lines = max_lines
        self._stats = self._compute_stats()

    def _compute_stats(self) -> tuple[int, int]:
        """Compute additions and deletions count.

        Returns:
            Tuple of (additions, deletions)
        """
        additions = 0
        deletions = 0
        for line in self._diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return additions, deletions

    def compose(self) -> ComposeResult:
        """Compose the diff widget layout."""
        yield Static(f"[#d0dbe7]{self._title}[/#d0dbe7]", classes="diff-title")

        formatted = format_diff_textual(self._diff, self._max_lines)
        yield Static(formatted, classes="diff-content")

        additions, deletions = self._stats
        if additions or deletions:
            stats_parts = []
            if additions:
                stats_parts.append(f"[#72d69f]+{additions}[/#72d69f]")
            if deletions:
                stats_parts.append(f"[#ff7a7a]-{deletions}[/#ff7a7a]")
            yield Static(" ".join(stats_parts), classes="diff-stats")
