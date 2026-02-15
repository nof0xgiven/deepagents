# Progress

## Current Status (February 15, 2026)
- Project is functional but in heavy active-refactor state.
- Core CLI runtime, agent wiring, and persistence paths are present.
- Command and model systems have recently been restructured.
- Slash command menu rendering and navigation bugs have been fixed.

## What Works
- CLI bootstrapping and Textual app launch path.
- Explicit model-selection workflow and model selector UI.
- Command registry with handlers for core/model/assemble flows.
- Extension loading and Morph tool registration.
- Memory/session persistence infrastructure (`MemoryMiddleware`, SQLite stores).
- Slash command menu renders outside ChatInput at the app level with proper sizing and styling.
- Keyboard navigation in slash menu scrolls to keep the highlighted item visible.
- All slash command items are accessible (menu scrolls when items exceed viewport).

## What Was Fixed (Slash Command Menu -- February 15, 2026)
- **Layout bug**: SlashCommandMenu was composed inside ChatInput (a Vertical container) and was constrained by its max-height and background. Moved to the app's `bottom-app-container` above ChatInput.
- **Communication pattern**: ChatInput now emits a `SlashMenuUpdate` message that bubbles to the app, which owns and controls the external SlashCommandMenu instance.
- **Scroll/navigation bug**: Menu extended `Vertical` (non-scrollable) and the parent viewport constrained visible height, so items past the visible rows were hidden and keyboard highlight was lost on scroll. Changed base class to `VerticalScroll`, added `scroll_visible()` on selected row, and added spacer recalculation on menu show/hide.
- **CSS**: Added `#slash-command-menu` styles to `app.tcss` with hidden scrollbar and proper visual treatment.

## In Progress
- End-to-end interactive validation of the slash command menu fix in a live session.
- Broad UI/visual refinement work documented in `docs/plans/2026-02-14-ghost-glass-*.md`.
- Consolidation/cleanup of many modified and newly added files in worktree.

## Not Started / Deferred
- Formal automated test harness documentation in README.
- Clear release checklist for validating command UX and extension combinations.

## Known Issues and Risks
- Large, mixed change surface increases regression risk until scoped and verified.
- No documented canonical test suite means quality depends on disciplined runtime proofs.
- UI redesign and command/input refactors can conflict if validated independently.

## Decision History (Recent)
- Slash command menu moved to app-level composition to avoid container clipping; ChatInput communicates state via message bubbling.
- `VerticalScroll` chosen as base class for `SlashCommandMenu` to ensure all items are reachable.
- Moved from ad-hoc command parsing to registry-driven command modules.
- Chosen architecture favors explicit state modules over large monolithic app logic.
- Slash menu behavior shifted to dedicated input logic instead of generic autocomplete internals.
