"""Welcome banner widget for deepagents-cli."""

from __future__ import annotations

import os
from typing import Any

from textual.widgets import Static

from deepagents_cli import theme
from deepagents_cli.config import settings


class WelcomeBanner(Static):
    """Welcome banner displayed at startup."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 2 2;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the welcome banner."""
        model = settings.model_name or "default"

        banner_text = f"[{theme.PRIMARY}]deepagents[/{theme.PRIMARY}]  [{theme.MUTED}]ready[/{theme.MUTED}]\n"
        banner_text += f"[{theme.SECONDARY}]using: {model}[/{theme.SECONDARY}]\n\n"

        # Show LangSmith status if tracing is enabled
        langsmith_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get(
            "LANGCHAIN_API_KEY"
        )
        langsmith_tracing = os.environ.get("LANGSMITH_TRACING") or os.environ.get(
            "LANGCHAIN_TRACING_V2"
        )

        if langsmith_key and langsmith_tracing:
            project = (
                settings.deepagents_langchain_project
                or os.environ.get("LANGSMITH_PROJECT")
                or "default"
            )
            banner_text += f"[{theme.MUTED}]tracing: {project}[/{theme.MUTED}]\n"

        banner_text += (
            f"[{theme.SECONDARY}]enter[/{theme.SECONDARY}] [{theme.HINT}]send[/{theme.HINT}]"
            f"  [{theme.HINT}]\u00b7[/{theme.HINT}]  "
            f"[{theme.SECONDARY}]ctrl+j[/{theme.SECONDARY}] [{theme.HINT}]newline[/{theme.HINT}]"
            f"  [{theme.HINT}]\u00b7[/{theme.HINT}]  "
            f"[{theme.SECONDARY}]@[/{theme.SECONDARY}] [{theme.HINT}]files[/{theme.HINT}]"
            f"  [{theme.HINT}]\u00b7[/{theme.HINT}]  "
            f"[{theme.SECONDARY}]/[/{theme.SECONDARY}] [{theme.HINT}]commands[/{theme.HINT}]"
            f"  [{theme.HINT}]\u00b7[/{theme.HINT}]  "
            f"[{theme.SECONDARY}]esc[/{theme.SECONDARY}] [{theme.HINT}]interrupt[/{theme.HINT}]"
        )
        super().__init__(banner_text, **kwargs)
