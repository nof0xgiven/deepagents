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
        stats_parts.append(f"[#4ade80]+{additions}[/#4ade80]")
    if deletions:
        stats_parts.append(f"[#f87171]-{deletions}[/#f87171]")
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
                f"[#3f3f46]{old_num:>{width}}[/#3f3f46] "
                f"[#f87171]-{escaped_content}[/#f87171]"
            )
            old_num += 1
            line_count += 1
        elif line.startswith("+"):
            formatted.append(
                f"[#3f3f46]{new_num:>{width}}[/#3f3f46] "
                f"[#4ade80]+{escaped_content}[/#4ade80]"
            )
            new_num += 1
            line_count += 1
        elif line.startswith(" "):
            formatted.append(f"[#3f3f46]{old_num:>{width}}[/#3f3f46]  {escaped_content}")
            old_num += 1
            new_num += 1
            line_count += 1
        elif line.strip() == "...":
            formatted.append("[#3f3f46]...[/#3f3f46]")
            line_count += 1

    return "\n".join(formatted)


class EnhancedDiff(Vertical):
    """Widget for displaying a unified diff with syntax highlighting."""

    DEFAULT_CSS = """
    EnhancedDiff {
        height: auto;
        padding: 1;
        background: #151515;
    }

    EnhancedDiff .diff-title {
        color: #71717a;
        margin-bottom: 1;
    }

    EnhancedDiff .diff-content {
        height: auto;
    }

    EnhancedDiff .diff-stats {
        color: #71717a;
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
        yield Static(f"[#71717a]{self._title}[/#71717a]", classes="diff-title")

        formatted = format_diff_textual(self._diff, self._max_lines)
        yield Static(formatted, classes="diff-content")

        additions, deletions = self._stats
        if additions or deletions:
            stats_parts = []
            if additions:
                stats_parts.append(f"[#4ade80]+{additions}[/#4ade80]")
            if deletions:
                stats_parts.append(f"[#f87171]-{deletions}[/#f87171]")
            yield Static(" ".join(stats_parts), classes="diff-stats")
