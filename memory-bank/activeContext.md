# Active Context

## Current Focus (as of February 15, 2026)
- Slash command menu rendering and interaction bugs have been resolved.
- Continue UI polish and stabilization work after the menu refactor.
- Keep the new command architecture and model/provider split coherent while UI redesign work continues.
- Preserve production-safe behavior while repo has substantial in-progress changes.

## Recent Changes
- **Slash command menu layout fix**: `SlashCommandMenu` was moved out of `ChatInput` (where it was cramped inside a Vertical container) into the app's `bottom-app-container` in `app.py`, positioned above `ChatInput`. This resolved the menu being constrained by `ChatInput`'s max-height and background styling.
- **Menu communication refactor**: `ChatInput` now emits a `SlashMenuUpdate` message that bubbles up to the app. The app handles this message in `on_chat_input_slash_menu_update` to control the external `SlashCommandMenu` instance.
- **Scroll and navigation fix**: `SlashCommandMenu` base class was changed from `Vertical` to `VerticalScroll` so all items are accessible. `scroll_visible()` is called on the selected row during keyboard navigation. Spacer height is recalculated on menu show/hide.
- **CSS additions**: External `#slash-command-menu` styling added to `app.tcss` with hidden scrollbar and proper visual treatment.
- Slash command handling was rebuilt in `ChatInput` with a dedicated slash menu flow (separate from `@` file autocomplete).
- Command handling was modularized into `src/deepagents_cli/commands/` with explicit registry + context.
- Model/provider concerns were separated into dedicated modules (`model_*`, `settings_store`, `provider_adapters`, `auth_store`).
- Linear ID parsing was centralized (`linear_ids.py`) and `/assemble` flow moved into dedicated command handler.

## Active Decisions
- Slash command menu lives at the app level (not inside ChatInput) to avoid container clipping and height constraints.
- Menu state is communicated from ChatInput to app via message bubbling (`SlashMenuUpdate`), keeping separation of concerns.
- `VerticalScroll` is the correct base for menus that may exceed visible viewport height.
- Keep command handlers small and isolated by concern (`core`, `model`, `assemble`).
- Maintain explicit model gating semantics before task execution.
- Prefer deterministic persistence flow for sessions/memory (`sessions.db`, `store.db`) over ad-hoc state.

## Immediate Next Steps
1. Smoke-test slash command menu end-to-end in a live `deepagents` session (rendering, scrolling, keyboard navigation, item selection).
2. Run project sanity checks (imports/compile + interactive smoke run) before packaging or release.
3. Decide whether Ghost Glass visual plan docs should be fully implemented now or tracked as pending design work.
4. Clean and scope repo changes for the next commit set.

## Notes
- Worktree currently includes broad in-progress modifications; keep scope discipline for each follow-up task.
- When updating memory bank later, `activeContext.md` and `progress.md` should be updated first.

## Key Files Changed (Slash Menu Fix)
- `src/deepagents_cli/widgets/chat_input.py` -- `SlashCommandMenu` changed to `VerticalScroll`, added `SlashMenuUpdate` message, removed menu from `compose()`.
- `src/deepagents_cli/app.py` -- Added `SlashCommandMenu` to app `compose()` above `ChatInput`, added `on_chat_input_slash_menu_update` handler.
- `src/deepagents_cli/app.tcss` -- Added external `#slash-command-menu` CSS with scrollbar hidden and proper styling.
