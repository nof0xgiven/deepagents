"""Modal model selector for deepagents-cli."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from deepagents_cli.model_registry import (
    ModelEntry,
    load_model_state,
    model_key,
    save_model_state,
    search_models,
    toggle_favorite,
    update_recent,
)


class ModelSelectorScreen(ModalScreen[ModelEntry | None]):
    """Modal screen for selecting models with search and favorites."""

    BINDINGS: list[BindingType] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("ctrl+f", "toggle_favorite", "Favorite", show=False),
    ]

    def __init__(
        self,
        *,
        entries: list[ModelEntry],
        current_model_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._entries = entries
        self._current_model_key = current_model_id
        self._state = load_model_state()
        self._favorites = set(self._state.get("favorites", []))
        self._filtered_entries: list[ModelEntry] = []

    def compose(self) -> ComposeResult:
        with Container(id="model-selector-panel"):
            yield Static("Select Model", id="model-selector-title")
            yield Input(
                placeholder="Search models...",
                classes="model-selector-input",
                id="search-input"
            )
            yield OptionList(id="model-selector-list")
            yield Static(
                "type to filter · ↓↑ navigate · enter select · esc cancel · ctrl+f favorite",
                id="model-selector-help",
            )

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one(Input).focus()

    def _format_option_text(self, entry: ModelEntry) -> Text:
        key = model_key(entry)
        is_fav = key in self._favorites
        is_active = self._current_model_key and key == self._current_model_key

        text = Text()
        
        # Star for favorites - subtle accent color
        if is_fav:
            text.append("★ ", style="#8cd8ff")
        else:
            text.append("  ")
        
        # Name - white for active, gray for normal
        name_style = "bold #f4f8fc" if is_active else "#d0dbe7"
        text.append(f"{entry.display_name:<28}", style=name_style)
        
        # Provider metadata
        text.append(f"{entry.provider:<12}", style="#aab8c6")
        
        # Details in subtle gray
        details = []
        if entry.context_window:
            if entry.context_window >= 1024:
                k_tokens = entry.context_window // 1024
                details.append(f"{k_tokens}k")
            else:
                details.append(f"{entry.context_window}")
        
        if entry.reasoning_effort:
            details.append(f"reason={entry.reasoning_effort}")
        
        if entry.service_tier:
            details.append(f"{entry.service_tier}")
            
        if is_active:
            details.append("ACTIVE")

        if details:
            text.append("  " + " · ".join(details), style="#8d9cab")

        return text

    def _format_header(self, title: str) -> Text:
        """Format section headers with subtle separators."""
        return Text(f"─ {title} ─", style="#9aa8b7 dim")

    def _refresh_list(self, query: str = "") -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        
        options = []
        
        if query:
            # Flat list of matches when searching
            matches = search_models(query, self._entries, limit=50)
            self._filtered_entries = matches
            
            if not matches:
                option_list.add_option(
                    Option(Text("No matches found", style="#9aa8b7 italic"), disabled=True)
                )
                return

            for entry in matches:
                txt = self._format_option_text(entry)
                options.append(Option(txt, id=model_key(entry)))
                
        else:
            # Grouped view when not searching
            # 1. Favorites
            fav_entries = [e for e in self._entries if model_key(e) in self._favorites]
            if fav_entries:
                options.append(Option(self._format_header("Favorites"), disabled=True))
                for entry in fav_entries:
                    txt = self._format_option_text(entry)
                    options.append(Option(txt, id=model_key(entry)))

            # 2. Recent
            recent_keys = self._state.get("recent", [])
            rec_entries = [
                e for e in self._entries 
                if model_key(e) in recent_keys and model_key(e) not in self._favorites
            ]
            if rec_entries:
                options.append(Option(self._format_header("Recent"), disabled=True))
                for entry in rec_entries:
                    txt = self._format_option_text(entry)
                    options.append(Option(txt, id=model_key(entry)))

            # 3. By Provider
            remaining = [
                e for e in self._entries 
                if model_key(e) not in self._favorites 
                and model_key(e) not in recent_keys
            ]
            
            by_provider: dict[str, list[ModelEntry]] = {}
            for entry in remaining:
                by_provider.setdefault(entry.provider, []).append(entry)
            
            for provider in sorted(by_provider.keys()):
                options.append(Option(self._format_header(provider), disabled=True))
                provider_models = sorted(by_provider[provider], key=lambda x: x.display_name)
                for entry in provider_models:
                    txt = self._format_option_text(entry)
                    options.append(Option(txt, id=model_key(entry)))
        
        option_list.add_options(options)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._select_option(event.option)

    def _select_option(self, option: Option) -> None:
        if option.disabled or not option.id:
            return

        model_id = option.id
        
        entry = next((e for e in self._entries if model_key(e) == model_id), None)
        if entry:
            update_recent(self._state, model_id)
            save_model_state(self._state)
            self.dismiss(entry)

    def action_move_down(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            option_list.highlighted = 0
        else:
            option_list.highlighted = min(option_list.highlighted + 1, option_list.option_count - 1)
        option_list.scroll_to_highlight()

    def action_move_up(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            option_list.highlighted = 0
        else:
            option_list.highlighted = max(option_list.highlighted - 1, 0)
        option_list.scroll_to_highlight()

    def action_select(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
        
        option = option_list.get_option_at_index(option_list.highlighted)
        self._select_option(option)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_toggle_favorite(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
            
        option = option_list.get_option_at_index(option_list.highlighted)
        if option.disabled or not option.id:
            return

        toggle_favorite(self._state, option.id)
        save_model_state(self._state)
        self._favorites = set(self._state.get("favorites", []))
        
        search_val = self.query_one(Input).value
        current_idx = option_list.highlighted
        self._refresh_list(search_val)
        
        if current_idx is not None and current_idx < option_list.option_count:
             option_list.highlighted = current_idx
