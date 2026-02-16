"""Welcome banner widget for deepagents-cli."""

from __future__ import annotations

import os
from typing import Any

from textual.widgets import Static

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
        banner_text = "[#f4f8fc]deepagents[/#f4f8fc]  [#9fb0c0]ready[/#9fb0c0]\n"
        banner_text += "[#b9c7d5]type your task or use /help[/#b9c7d5]\n\n"

        # Show LangSmith status if tracing is enabled
        langsmith_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
        langsmith_tracing = os.environ.get("LANGSMITH_TRACING") or os.environ.get(
            "LANGCHAIN_TRACING_V2"
        )

        if langsmith_key and langsmith_tracing:
            project = (
                settings.deepagents_langchain_project
                or os.environ.get("LANGSMITH_PROJECT")
                or "default"
            )
            banner_text += f"[#9fb0c0]tracing: {project}[/#9fb0c0]\n"

        banner_text += (
            "[#8fa1b3]enter send · ctrl+j newline · @ files · / commands · esc interrupt[/#8fa1b3]"
        )
        super().__init__(banner_text, **kwargs)
