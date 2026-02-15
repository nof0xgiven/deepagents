# Ghost Glass TUI Redesign

## Summary

Full visual overhaul of the deepagents-cli TUI with minor UX tweaks. The philosophy: **the absence of design is the design.** Everything that isn't content fades to near-invisibility. Three accent uses create tiny moments of electric blue that feel precious because they're so rare.

Inspiration: macOS window chrome, Linear, Notion minimal, Cursor, Vercel dashboard.

## Color System

The entire palette is 5 grays plus one accent.

| Token     | Hex       | Use                                                     |
|-----------|-----------|---------------------------------------------------------|
| `void`    | `#09090b` | App background — true black                             |
| `surface` | `#0f0f11` | Message cards, input area — barely visible lift          |
| `raised`  | `#161618` | Hovered/active surfaces, approval card                  |
| `muted`   | `#3f3f46` | Borders (when absolutely necessary), dividers           |
| `dim`     | `#71717a` | Secondary text, timestamps, labels                      |
| `text`    | `#e4e4e7` | Primary text — warm white, not harsh                    |
| `accent`  | `#00AEEF` | 3 uses only: active input caret, selected approval option, streaming indicator |

Functional colors are desaturated and quiet:

| State       | Color     | Notes                     |
|-------------|-----------|---------------------------|
| Error text  | `#ef4444` | No background card        |
| Diff add    | `#4ade80` | Text only, no background  |
| Diff remove | `#f87171` | Text only, no background  |

**Rule:** If you can remove a color, remove it. If it still works, it was never needed.

## Typography & Spacing

Hierarchy through weight and opacity, not color or size.

- **Primary text:** `#e4e4e7` — full brightness
- **Secondary text:** `#71717a` — 50% dimmer
- **Ghost text:** `#3f3f46` — nearly invisible, for hints and help

Spacing is generous. Content breathes.

- Messages separated by 1 empty line (not borders)
- Chat area padding: `2 3`
- Input area padding: `1 3` to align with chat
- If something feels tight, add space, not a border

## Messages

### User Messages
- No border, no background
- Dim `>` prompt in `#3f3f46`
- Text in `#e4e4e7`

### Assistant Messages
- Background: `surface` (`#0f0f11`) — faintest card
- No border, no left accent
- Padding: `1 2` inside the card

### Tool Call Messages
- Collapsed by default — single line: dim `◆` + tool name + brief summary in `#71717a`
- Expanded: `surface` background card, content in `dim`
- No colored status badges. Success = dim `✓`. Error = dim `✗`.
- No colored left-borders

### Error Messages
- No red background card
- Text in `#ef4444` with dim `✗` prefix

### System Messages
- Ghost text `#3f3f46` — nearly invisible

## Input Area

- No visible border on the text area
- Prompt `>` in `#3f3f46`, becomes `#00AEEF` when agent is idle and ready
- Background matches `void` — no card, no boundary
- Text in `#e4e4e7`
- Completion popup: `raised` background, no border, selected item in `#e4e4e7` with accent left marker

## Status Bar

A whisper at the bottom.

- Height: 1 line, docked to bottom
- Background: `void` — invisible boundary
- All text `#3f3f46`, separated by ` · `
- Layout: `mode · auto · status · tokens · model`
- Mode: just the word "bash"/"cmd" in dim, no colored badge
- Auto-approve: "manual"/"auto" in dim, no color
- Model: `#71717a` — slightly brighter
- Feels like metadata you can ignore

## Approval Workflow

- Card background: `raised` (`#161618`)
- No border — the background shift is the boundary
- Title: tool name in `#e4e4e7`, "requires approval" in `#71717a`
- Tool info: `raised` background, dim text
- Options:
  - Unselected: `#71717a` on `raised`
  - Selected: `#e4e4e7` on `surface` with thin `accent` left bar
- Help text: ghost gray `#3f3f46`

## Welcome Banner

- No ASCII art
- `deepagents` in `#e4e4e7`
- `ready` in `#3f3f46`
- Keyboard hints in ghost text: `enter send · ctrl+j newline · @ files · / commands`
- Generous vertical padding — emptiness is the design

## Model Selector Modal

- Background: `raised`
- No border. 1-cell `void` gap around modal simulates depth
- Search: no border, blinking cursor, ghost placeholder
- List: plain text
  - Active model: `#e4e4e7` with `(active)` in ghost text
  - Favorite: `★` in `#71717a`
  - Selected: `surface` background + accent left marker
- Provider labels in ghost text, no divider lines

## Diff Rendering

- No colored backgrounds
- Additions: `#4ade80` text, no background
- Deletions: `#f87171` text, no background
- Context: `#3f3f46`
- Line numbers: `#3f3f46`
- No gutter bars — `+`/`-` prefixes are enough
- Stats: `+N -N` in respective colors

## Loading / Thinking

- Braille spinner in `#71717a`
- Status text: `thinking` in `#71717a`, elapsed in `#3f3f46`
- No warning/yellow color
- When streaming, `>` prompt pulses `accent` blue

## UX Tweaks

1. **Message grouping:** 1 blank line between user-assistant exchanges, 0 between consecutive tool calls. Creates visual turns.
2. **Tool call collapse:** Default collapsed for all tool calls. Click or Ctrl+O to expand.
3. **Model name truncation:** Show last segment only (e.g. `opus-4-6` not `claude-opus-4-6`).

## Files to Change

| File | Scope |
|------|-------|
| `app.tcss` | Full rewrite — new color system, spacing, all component styles |
| `app.py` | Minor — update compose() for spacing tweaks, message grouping logic |
| `widgets/status.py` | Restyle — remove colored badges, ghost text, dot separators |
| `widgets/messages.py` | Restyle all message types, strip borders/backgrounds |
| `widgets/approval.py` | Restyle card, options, remove yellow border |
| `widgets/chat_input.py` | Strip input borders, ghost prompt, accent-on-ready |
| `widgets/loading.py` | Remove warning color, dim spinner |
| `widgets/welcome.py` | Strip ASCII art, minimal text |
| `widgets/model_selector.py` | Ghost modal, strip borders |
| `widgets/tool_renderers.py` | Desaturated diffs, no background colors |
| `widgets/autocomplete.py` | Ghost popup styling |
| `ui.py` | Update format helpers if needed |
| `diff.py` | Strip colored backgrounds, simplify gutter |
