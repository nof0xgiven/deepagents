Now I have a complete understanding of the codebase. Let me create the context package.

# Context Package: Subagent Streaming Panel

## Task Understanding

The user wants to see streaming output from subagents within a dedicated panel in the UI. Currently, when the main agent uses the `task` tool to launch a subagent, the subagent runs in the background and its streaming output is completely hidden. The user only sees a badge showing "agents: N running" but has no visibility into what each subagent is doing. The solution requires creating a subagent panel widget that captures and displays the streaming content (text, tool calls, progress) from each active subagent, allowing the user to see that work is progressing.

**Type:** feature
**Scope:** `src/deepagents_cli/widgets/` (new widget), `src/deepagents_cli/textual_adapter.py` (streaming routing), `src/deepagents_cli/app.py` (panel management), `src/deepagents_cli/app.tcss` (styling)
**Complexity:** medium - requires coordinating streaming data flow between adapter and UI, plus new widget creation

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      DeepAgentsApp                          │
├─────────────────────────────────────────────────────────────┤
│  #chat (VerticalScroll)                                     │
│  ├── #messages (Container)                                  │
│  │   ├── UserMessage                                        │
│  │   ├── AssistantMessage (main agent)                      │
│  │   ├── ToolCallMessage                                    │
│  │   └── [NEW] SubagentPanel(s)  ← mounted per subagent     │
│  │       ├── SubagentHeader (name, status, elapsed)         │
│  │       └── SubagentContent (streaming output)             │
│  └── WelcomeBanner                                          │
├─────────────────────────────────────────────────────────────┤
│  #bottom-app-container                                      │
│  ├── ChatInput                                              │
│  └── StatusBar + AgentsPill                                 │
└─────────────────────────────────────────────────────────────┘
```

**Streaming Data Flow:**
```
agent.astream(subgraphs=True)
    │
    ├── namespace = ()      → Main agent → AssistantMessage (existing)
    │
    └── namespace = ('task', 'subagent-id')  → Subagent
            │
            └── [MODIFIED] Route to SubagentPanel by namespace
```

**Key Modules:**
- `src/deepagents_cli/textual_adapter.py` - Routes streaming chunks to appropriate widgets by namespace
- `src/deepagents_cli/widgets/messages.py` - Contains `AssistantMessage`, `ToolCallMessage` patterns to follow
- `src/deepagents_cli/widgets/loading.py` - Contains `LoadingWidget`, `BrailleSpinner` patterns for progress indication
- `src/deepagents_cli/app.py` - Manages widget lifecycle, receives subagent start/end callbacks

---

## Files to Read

### Must Read (Core to the task)
| File | Lines | Why |
|------|-------|-----|
| `src/deepagents_cli/textual_adapter.py` | 1-350 | Contains streaming logic that currently filters out subagent content; needs modification to route to panels |
| `src/deepagents_cli/textual_adapter.py` | 500-733 | Shows how text/tool calls are rendered, stream finalization |
| `src/deepagents_cli/widgets/messages.py` | 57-150 | `AssistantMessage` pattern - streaming markdown via `MarkdownStream` |
| `src/deepagents_cli/widgets/messages.py` | 152-350 | `ToolCallMessage` pattern - status icons, executing state, spinner |
| `src/deepagents_cli/widgets/loading.py` | full | `LoadingWidget` pattern - elapsed time, spinner animation |
| `src/deepagents_cli/app.py` | 343-380 | Subagent stream start/end callbacks, agents pill refresh |

### Should Read (Patterns to follow)
| File | Lines | Why |
|------|-------|-----|
| `src/deepagents_cli/widgets/agents_pill.py` | full | Shows how subagent count is tracked and displayed |
| `src/deepagents_cli/app.py` | 198-260 | App compose and mount pattern |
| `src/deepagents_cli/app.tcss` | 110-131 | Agents pill styling pattern |
| `src/deepagents_cli/background_tasks.py` | 294-338 | `BackgroundTaskMiddleware` - shows how task tool is intercepted |

### Optional (Background context)
| File | Lines | Why |
|------|-------|-----|
| `src/deepagents_cli/ui.py` | 148-155 | `format_tool_display` for task tool |
| `src/deepagents_cli/agent.py` | 746-770 | `_format_task_description` for task approval |

---

## Files to Create/Modify

| Action | File | Description |
|--------|------|-------------|
| CREATE | `src/deepagents_cli/widgets/subagent_panel.py` | New widget for displaying subagent streaming output |
| MODIFY | `src/deepagents_cli/textual_adapter.py` | Route subagent namespace content to panels instead of skipping |
| MODIFY | `src/deepagents_cli/app.py` | Add `on_subagent_content` callback, manage panel lifecycle |
| MODIFY | `src/deepagents_cli/app.tcss` | Add styling for SubagentPanel |
| MODIFY | `src/deepagents_cli/widgets/__init__.py` | Export new widget |

---

## Patterns to Follow

### Streaming Message Pattern (from AssistantMessage)
```python
# From: src/deepagents_cli/widgets/messages.py (lines 57-150)
class AssistantMessage(Vertical):
    """Widget displaying an assistant message with markdown support.
    Uses MarkdownStream for smoother streaming instead of re-rendering.
    """
    
    def __init__(self, content: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._content = content
        self._markdown: Markdown | None = None
        self._stream: MarkdownStream | None = None

    def _ensure_stream(self) -> MarkdownStream:
        """Ensure the markdown stream is initialized."""
        if self._stream is None:
            self._stream = Markdown.get_stream(self._get_markdown())
        return self._stream

    async def append_content(self, text: str) -> None:
        """Append content to the message (for streaming)."""
        if not text:
            return
        self._content += text
        stream = self._ensure_stream()
        await stream.write(text)

    async def stop_stream(self) -> None:
        """Stop the streaming and finalize the content."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None
```

### Executing/Progress Pattern (from ToolCallMessage)
```python
# From: src/deepagents_cli/widgets/messages.py (lines 319-346)
_LONG_RUNNING_TOOLS = {"task"}

def _start_executing(self) -> None:
    """Start the executing indicator for long-running tools."""
    self._executing_start_time = time()
    self._spinner = BrailleSpinner()
    if self._status_widget:
        self._status_widget.update(f"{self._spinner.current_frame()} working... (0s)")
        self._status_widget.add_class("executing")
        self._status_widget.display = True
    self._executing_timer = self.set_interval(0.1, self._update_executing)

def _update_executing(self) -> None:
    """Update the executing spinner and elapsed time."""
    if self._spinner and self._status_widget:
        frame = self._spinner.next_frame()
        elapsed = int(time() - self._executing_start_time)
        self._status_widget.update(f"{frame} working... ({elapsed}s)")
```

### Subagent Namespace Detection (from textual_adapter.py)
```python
# From: src/deepagents_cli/textual_adapter.py (lines 282-324)
namespace, current_stream_mode, data = chunk

# Convert namespace to hashable tuple for dict keys
ns_key = tuple(namespace) if namespace else ()
await _emit_subagent_start(ns_key)

# Filter out subagent outputs - only show main agent (empty namespace)
# Subagents run via Task tool and should only report back to the main agent
is_main_agent = ns_key == ()

# Handle MESSAGES stream - for content and tool calls
elif current_stream_mode == "messages":
    # Skip subagent outputs - only render main agent content in chat
    if not is_main_agent:
        if isinstance(data, tuple) and len(data) == 2:
            subagent_message, _ = data
            if getattr(subagent_message, "chunk_position", None) == "last":
                await _emit_subagent_end(ns_key)
        continue  # <-- THIS IS WHERE SUBAGENT CONTENT IS CURRENTLY DROPPED
```

---

## Type Definitions

```python
# New types for subagent panel management

# Namespace key type (already used in codebase)
NamespaceKey = tuple[str, ...]  # e.g., (), ('task', 'scout-1')

# Subagent info for panel display
@dataclass
class SubagentInfo:
    """Information about an active subagent."""
    namespace: NamespaceKey
    subagent_type: str  # e.g., "scout", "worker", "planner"
    task_id: str | None  # Background task ID if applicable
    description: str  # Brief description of what it's doing
    start_time: float  # monotonic time
```

---

## Dependencies & Imports

```python
# For new subagent_panel.py widget
from __future__ import annotations
from time import time
from typing import TYPE_CHECKING, Any

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Markdown
from textual.widgets._markdown import MarkdownStream
from textual.timer import Timer

from deepagents_cli import theme
from deepagents_cli.widgets.loading import BrailleSpinner

if TYPE_CHECKING:
    from textual.app import ComposeResult

# For textual_adapter.py modifications
from deepagents_cli.widgets.subagent_panel import SubagentPanel

# For app.py modifications
from deepagents_cli.widgets.subagent_panel import SubagentPanel
```

---

## Constraints & Requirements

- [ ] Must display streaming content from subagents in real-time
- [ ] Must show subagent type/name and elapsed time
- [ ] Must handle multiple concurrent subagents (each gets own panel)
- [ ] Must clean up panels when subagent completes
- [ ] Must not interfere with main agent message flow
- [ ] Should be collapsible or have a max height to not overwhelm chat
- [ ] Should show tool calls made by subagent (simplified view)
- [ ] Must integrate with existing `on_subagent_start`/`on_subagent_end` callbacks

---

## Potential Gotchas

1. **Namespace format** - The namespace from LangGraph is a list of strings, needs to be converted to tuple for dict keys. Already done in code: `ns_key = tuple(namespace) if namespace else ()`

2. **Stream mode handling** - Chunks come in two modes: `"messages"` (content/tool calls) and `"updates"` (interrupts/todos). Both need to be routed to panels for subagents.

3. **Panel lifecycle** - Panels must be mounted when subagent starts and removed/completed when subagent ends. The `_emit_subagent_start` and `_emit_subagent_end` callbacks already exist but need to be extended.

4. **Multiple subagents** - The code already tracks `active_subagent_namespaces: set[tuple]` and `assistant_message_by_namespace: dict[tuple, Any]`. Need similar pattern for panels.

5. **Background tasks vs streaming** - Subagents can be launched via `task` tool (background) or directly. Background tasks return immediately with task ID, but streaming still happens. Need to correlate task IDs with namespaces.

6. **Scroll behavior** - When subagent content streams, should chat auto-scroll? Probably yes, but user might be reading older content. Consider using `scroll_to_bottom` only when already at bottom.

7. **Tool call rendering** - Subagent tool calls should be shown but in a more compact form than main agent. Consider a simplified inline format.

---

## Questions Resolved

- Q: Should subagent panels be inline in chat or a separate sidebar?
  A: Inline in chat, similar to how `ToolCallMessage` appears. This keeps the conversation flow natural and doesn't require complex layout changes.

- Q: Should completed subagent panels remain visible?
  A: Yes, they should remain visible but show a "completed" status. This provides a record of what each subagent did.

- Q: How to handle subagent tool call approvals (HITL)?
  A: Subagents can have their own HITL interrupts. These should be handled the same way as main agent approvals - inline in the chat. The namespace tracking already supports this.

---

## Implementation Hints

1. **Create SubagentPanel widget** - A container with:
   - Header showing subagent type, status (running/completed), elapsed time
   - Content area using `MarkdownStream` for text
   - Simplified tool call display (inline, not full ToolCallMessage)
   - Spinner animation while running

2. **Modify textual_adapter.py** - Instead of `continue` when `not is_main_agent`:
   - Get or create `SubagentPanel` for the namespace
   - Route text chunks to panel's `append_content`
   - Route tool calls to panel's tool display
   - Handle stream end to stop panel's stream

3. **Extend app.py callbacks** - `_on_subagent_stream_start` should:
   - Create and mount a `SubagentPanel` 
   - Store reference in `self._subagent_panels: dict[tuple, SubagentPanel]`
   - `_on_subagent_stream_end` should mark panel as completed

4. **Add CSS styling** - Panel should be visually distinct from main messages:
   - Slightly indented or with different border color
   - Dimmed text or background to indicate "subagent activity"
   - Collapsible or max-height with scroll

5. **Content routing** - In `execute_task_textual`, when `not is_main_agent`:
   ```python
   if not is_main_agent:
       # Get panel for this namespace
       panel = await _get_or_create_subagent_panel(ns_key, adapter)
       # Route content to panel instead of skipping
       if isinstance(message, AIMessageChunk):
           # ... handle text/tool calls into panel
       if getattr(message, "chunk_position", None) == "last":
           panel.mark_completed()
       continue  # Still don't show in main chat
   ```