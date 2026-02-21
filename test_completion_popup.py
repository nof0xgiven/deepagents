"""Regression tests for @ file-completion popup visibility."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from deepagents_cli.widgets.chat_input import ChatInput, CompletionPopup


class _ChatInputProbeApp(App[None]):
    CSS_PATH = "src/deepagents_cli/app.tcss"

    def compose(self) -> ComposeResult:
        yield ChatInput(cwd=Path(__file__).resolve().parent)


async def test_file_completion_popup_has_visible_surface() -> None:
    """@ completion popup should have an explicit visible background surface."""
    app = _ChatInputProbeApp()

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        text_area = app.query_one("#chat-input")
        text_area.insert("@")
        await pilot.pause()

        popup = app.query_one("#completion-popup", CompletionPopup)
        assert str(popup.styles.display) == "block"
        assert popup.content.plain.strip() != ""
        assert popup.styles.background.a > 0, (
            "Completion popup background is fully transparent and can become unreadable "
            "against terminal backgrounds."
        )
