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
        padding: 3 3;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the welcome banner."""
        banner_text = "[#e4e4e7]deepagents[/#e4e4e7]  [#3f3f46]ready[/#3f3f46]\n\n"

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
            banner_text += f"[#3f3f46]tracing: {project}[/#3f3f46]\n"

        banner_text += "[#3f3f46]enter send · ctrl+j newline · @ files · / commands[/#3f3f46]"
        super().__init__(banner_text, **kwargs)
