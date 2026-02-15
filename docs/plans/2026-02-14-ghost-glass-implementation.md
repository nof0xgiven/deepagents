# Ghost Glass TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restyle the entire deepagents-cli TUI to the Ghost Glass design — ultra-minimal, near-invisible UI with 5 grays + 1 accent color.

**Architecture:** Modify DEFAULT_CSS in each widget + rewrite app.tcss. No structural changes to widget trees or logic. Pure visual overhaul with 3 minor UX tweaks (message grouping spacing, tool call collapse-by-default, model name truncation).

**Tech Stack:** Python Textual framework, TCSS stylesheets, Rich markup for inline styling.

---

## Color Reference (Ghost Glass Palette)

```
void    = #09090b  (app background)
surface = #0f0f11  (message cards, input area)
raised  = #161618  (hovered/active surfaces, approval card)
muted   = #3f3f46  (borders when necessary, dividers)
dim     = #71717a  (secondary text, timestamps, labels)
text    = #e4e4e7  (primary text)
accent  = #00AEEF  (3 uses ONLY: active input caret, selected approval, streaming indicator)

error   = #ef4444  (error text, no background)
diff-add = #4ade80 (text only)
diff-rm  = #f87171 (text only)
```

---

### Task 1: Rewrite app.tcss — New Color System & Layout

**Files:**
- Modify: `src/deepagents_cli/app.tcss` (all 230 lines)

**Step 1: Rewrite app.tcss with Ghost Glass styles**

Replace the entire file with:

```css
/* Ghost Glass — DeepAgents CLI */

Screen {
    layout: vertical;
    layers: base autocomplete modal;
    background: #09090b;
}

/* Chat area */
#chat {
    height: 1fr;
    padding: 2 3;
    background: #09090b;
}

#chat-spacer {
    height: auto;
}

/* Welcome banner */
#welcome-banner {
    height: auto;
    margin-bottom: 1;
    padding: 2 0;
}

/* Messages area */
#messages {
    height: auto;
}

/* Bottom app container */
#bottom-app-container {
    height: auto;
    margin-top: 1;
    padding: 0 0;
}

/* Input area */
#input-area {
    height: auto;
    min-height: 3;
    max-height: 12;
}

/* Approval Menu */
.approval-menu {
    height: auto;
    margin: 1 0;
    padding: 1 2;
    background: #161618;
}

.approval-menu .approval-title {
    color: #e4e4e7;
    margin-bottom: 0;
}

.approval-menu .approval-info {
    height: auto;
    color: #71717a;
    margin-bottom: 1;
}

.approval-menu .approval-option {
    height: 1;
    padding: 0 1;
    color: #71717a;
}

.approval-menu .approval-option-selected {
    background: #0f0f11;
    color: #e4e4e7;
    border-left: thick #00AEEF;
}

.approval-menu .approval-help {
    color: #3f3f46;
    margin-top: 0;
    margin-bottom: 0;
}

/* Status bar */
#status-bar {
    height: 1;
    dock: bottom;
    margin-bottom: 0;
}

/* Tool approval widgets */
.tool-approval-widget {
    height: auto;
}

.approval-file-path {
    color: #e4e4e7;
}

.approval-description {
    color: #71717a;
}

/* Diff styling (in approval context) */
.diff-header {
    height: auto;
    color: #71717a;
}

.diff-removed {
    height: auto;
    color: #f87171;
    padding: 0 1;
}

.diff-added {
    height: auto;
    color: #4ade80;
    padding: 0 1;
}

.diff-range {
    height: auto;
    color: #71717a;
}

.diff-context {
    height: auto;
    color: #3f3f46;
    padding: 0 1;
}

/* Separator */
.approval-menu .approval-separator {
    height: 1;
    color: #3f3f46;
    margin: 0;
}

/* Scrollable tool info */
.approval-menu .tool-info-scroll {
    height: 10;
    margin-top: 0;
}

.approval-menu .tool-info-container {
    height: auto;
}

/* Options container */
.approval-menu .approval-options-container {
    height: auto;
    background: #161618;
    padding: 0 1;
    margin-top: 0;
}

/* Completion popup */
#completion-popup {
    height: auto;
    max-height: 12;
    width: 100%;
    margin-left: 3;
    margin-top: 0;
    padding: 0;
    background: #161618;
    color: #e4e4e7;
}

/* Model selector modal */
ModelSelectorScreen {
    align: center middle;
    background: #09090b 80%;
}

#model-selector-panel {
    layer: modal;
    width: 80%;
    max-width: 80;
    height: 24;
    background: #161618;
    padding: 1 2;
    align: center middle;
}

#model-selector-title {
    color: #e4e4e7;
    margin-bottom: 0;
}

#model-selector-search {
    color: #71717a;
    margin-bottom: 1;
}

#model-selector-scroll {
    height: 1fr;
}

#model-selector-scroll .model-row {
    height: 1;
    padding: 0 1;
}

#model-selector-scroll .model-row-selected {
    background: #0f0f11;
    color: #e4e4e7;
    border-left: thick #00AEEF;
}

#model-selector-scroll .model-header {
    color: #3f3f46;
    margin-top: 1;
}

#model-selector-help {
    color: #3f3f46;
    margin-top: 1;
}
```

**Step 2: Verify the app still launches**

Run: `cd /Users/ava/main/deep && python -m deepagents_cli --help`
Expected: No import/syntax errors.

**Step 3: Commit**

```bash
git add src/deepagents_cli/app.tcss
git commit -m "style: rewrite app.tcss with Ghost Glass color system"
```

---

### Task 2: Restyle StatusBar — Ghost Whisper

**Files:**
- Modify: `src/deepagents_cli/widgets/status.py:22-92` (DEFAULT_CSS block)
- Modify: `src/deepagents_cli/widgets/status.py:111-121` (compose method)
- Modify: `src/deepagents_cli/widgets/status.py:127-143` (watch_mode)
- Modify: `src/deepagents_cli/widgets/status.py:145-158` (watch_auto_approve)
- Modify: `src/deepagents_cli/widgets/status.py:168-181` (watch_status_message)

**Step 1: Replace DEFAULT_CSS in StatusBar**

Replace lines 22-92 with:

```python
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: #09090b;
        padding: 0 1;
    }

    StatusBar .status-mode {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-mode.normal {
        display: none;
    }

    StatusBar .status-mode.bash {
        color: #3f3f46;
    }

    StatusBar .status-mode.command {
        color: #3f3f46;
    }

    StatusBar .status-separator {
        width: auto;
        color: #3f3f46;
    }

    StatusBar .status-auto-approve {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-message {
        width: 1fr;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-message.thinking {
        color: #71717a;
    }

    StatusBar .status-tokens {
        width: auto;
        padding: 0 1;
        color: #3f3f46;
    }

    StatusBar .status-model {
        width: auto;
        padding: 0 1;
        color: #71717a;
    }
    """
```

**Step 2: Update compose() to use dot separators**

Replace lines 111-121 with:

```python
    def compose(self) -> ComposeResult:
        """Compose the status bar layout."""
        yield Static("", classes="status-mode normal", id="mode-indicator")
        yield Static(" · ", classes="status-separator")
        yield Static(
            "manual",
            classes="status-auto-approve",
            id="auto-approve-indicator",
        )
        yield Static(" · ", classes="status-separator")
        yield Static("", classes="status-message", id="status-message")
        yield Static("", classes="status-tokens", id="tokens-display")
        yield Static(" · ", classes="status-separator")
        yield Static(settings.model_name or "", classes="status-model", id="model-display")
```

**Step 3: Update watch_mode to remove colored badges**

Replace lines 127-143 — keep the method but update labels to lowercase, no colored background:

```python
    def watch_mode(self, mode: str) -> None:
        """Update mode indicator when mode changes."""
        try:
            indicator = self.query_one("#mode-indicator", Static)
        except NoMatches:
            return
        indicator.remove_class("normal", "bash", "command")

        if mode == "bash":
            indicator.update("bash")
            indicator.add_class("bash")
        elif mode == "command":
            indicator.update("cmd")
            indicator.add_class("command")
        else:
            indicator.update("")
            indicator.add_class("normal")
```

**Step 4: Update watch_auto_approve to remove colored badges**

Replace lines 145-158:

```python
    def watch_auto_approve(self, new_value: bool) -> None:  # noqa: FBT001
        """Update auto-approve indicator when state changes."""
        try:
            indicator = self.query_one("#auto-approve-indicator", Static)
        except NoMatches:
            return
        if new_value:
            indicator.update("auto")
        else:
            indicator.update("manual")
```

**Step 5: Update watch_status_message to remove warning color**

Replace lines 168-181:

```python
    def watch_status_message(self, new_value: str) -> None:
        """Update status message display."""
        try:
            msg_widget = self.query_one("#status-message", Static)
        except NoMatches:
            return

        msg_widget.remove_class("thinking")
        if new_value:
            msg_widget.update(new_value)
            if "thinking" in new_value.lower() or "executing" in new_value.lower():
                msg_widget.add_class("thinking")
        else:
            msg_widget.update("")
```

**Step 6: Verify app launches**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.status import StatusBar; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add src/deepagents_cli/widgets/status.py
git commit -m "style: restyle StatusBar with ghost whisper design"
```

---

### Task 3: Restyle WelcomeBanner — Minimal Text

**Files:**
- Modify: `src/deepagents_cli/widgets/welcome.py:13-45` (entire WelcomeBanner class)

**Step 1: Replace WelcomeBanner class**

Replace lines 13-45 with:

```python
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
```

**Step 2: Remove unused DEEP_AGENTS_ASCII import if it was only used here**

Check if `DEEP_AGENTS_ASCII` is used elsewhere. If only in welcome.py, remove the import on line 10:

Change:
```python
from deepagents_cli.config import DEEP_AGENTS_ASCII, settings
```
To:
```python
from deepagents_cli.config import settings
```

**Step 3: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.welcome import WelcomeBanner; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/deepagents_cli/widgets/welcome.py
git commit -m "style: strip ASCII art, minimal welcome banner"
```

---

### Task 4: Restyle LoadingWidget — Dim Spinner

**Files:**
- Modify: `src/deepagents_cli/widgets/loading.py:52-78` (DEFAULT_CSS)
- Modify: `src/deepagents_cli/widgets/loading.py:120` (spinner color in _update_animation)

**Step 1: Replace DEFAULT_CSS in LoadingWidget**

Replace lines 52-78 with:

```python
    DEFAULT_CSS = """
    LoadingWidget {
        height: auto;
        padding: 0 1;
    }

    LoadingWidget .loading-container {
        height: auto;
        width: 100%;
    }

    LoadingWidget .loading-spinner {
        width: auto;
        color: #71717a;
    }

    LoadingWidget .loading-status {
        width: auto;
        color: #71717a;
    }

    LoadingWidget .loading-hint {
        width: auto;
        color: #3f3f46;
        margin-left: 1;
    }
    """
```

**Step 2: Update spinner frame color**

Replace line 120:

```python
            self._spinner_widget.update(f"[#FFD800]{frame}[/]")
```

With:

```python
            self._spinner_widget.update(f"[#71717a]{frame}[/]")
```

**Step 3: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.loading import LoadingWidget; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/deepagents_cli/widgets/loading.py
git commit -m "style: dim spinner, remove warning colors from loading"
```

---

### Task 5: Restyle Messages — Ghost Cards

**Files:**
- Modify: `src/deepagents_cli/widgets/messages.py`

This is the largest single change. Each message type gets restyled.

**Step 1: Restyle UserMessage (lines 25-42 DEFAULT_CSS + line 58 compose)**

Replace DEFAULT_CSS (lines 25-42):

```python
    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    """
```

Replace the compose method body (lines 54-60):

```python
    def compose(self) -> ComposeResult:
        """Compose the user message layout."""
        text = Text()
        text.append("> ", style="#3f3f46")
        text.append(self._content, style="#e4e4e7")
        yield Static(text)
```

**Step 2: Restyle AssistantMessage (lines 70-81 DEFAULT_CSS)**

Replace DEFAULT_CSS:

```python
    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        padding: 1 2;
        margin: 1 0;
        background: #0f0f11;
    }

    AssistantMessage Markdown {
        padding: 0;
        margin: 0;
    }
    """
```

**Step 3: Restyle ToolCallMessage (lines 163-226 DEFAULT_CSS + line 261 compose header)**

Replace DEFAULT_CSS (lines 163-226):

```python
    DEFAULT_CSS = """
    ToolCallMessage {
        height: auto;
        padding: 0 1;
        margin: 0 0;
        background: #0f0f11;
    }

    ToolCallMessage .tool-header {
        color: #71717a;
    }

    ToolCallMessage .tool-args {
        color: #3f3f46;
        margin-left: 2;
    }

    ToolCallMessage .tool-status {
        margin-left: 2;
    }

    ToolCallMessage .tool-status.pending {
        color: #71717a;
    }

    ToolCallMessage .tool-status.success {
        color: #71717a;
    }

    ToolCallMessage .tool-status.error {
        color: #ef4444;
    }

    ToolCallMessage .tool-status.rejected {
        color: #71717a;
    }

    ToolCallMessage .tool-output {
        margin-left: 2;
        margin-top: 1;
        padding: 1;
        background: #0f0f11;
        color: #71717a;
        max-height: 20;
        overflow-y: auto;
    }

    ToolCallMessage .tool-output-preview {
        margin-left: 2;
        color: #71717a;
    }

    ToolCallMessage .tool-output-hint {
        margin-left: 2;
        color: #3f3f46;
    }
    """
```

Replace the tool header in compose (line 261):

```python
        yield Static(
            f"[#71717a]◆[/#71717a] {tool_label}",
            classes="tool-header",
        )
```

**Step 4: Update set_error and set_rejected markup (lines 310, 321, 329)**

Line 310 — change `[red]✗ Error[/red]` to `[#ef4444]✗[/#ef4444]`:

```python
            self._status_widget.update("[#ef4444]✗[/#ef4444]")
```

Line 321 — change `[yellow]✗ Rejected[/yellow]` to `[#71717a]✗ rejected[/#71717a]`:

```python
            self._status_widget.update("[#71717a]✗ rejected[/#71717a]")
```

Line 329 — change `[dim]- Skipped[/dim]` to `[#3f3f46]- skipped[/#3f3f46]`:

```python
            self._status_widget.update("[#3f3f46]- skipped[/#3f3f46]")
```

**Step 5: Restyle DiffMessage (lines 411-443 DEFAULT_CSS)**

Replace DEFAULT_CSS:

```python
    DEFAULT_CSS = """
    DiffMessage {
        height: auto;
        padding: 1;
        margin: 1 0;
    }

    DiffMessage .diff-header {
        margin-bottom: 1;
    }

    DiffMessage .diff-add {
        color: #4ade80;
    }

    DiffMessage .diff-remove {
        color: #f87171;
    }

    DiffMessage .diff-context {
        color: #3f3f46;
    }

    DiffMessage .diff-hunk {
        color: #71717a;
    }
    """
```

**Step 6: Restyle ErrorMessage (lines 470-479 DEFAULT_CSS + line 489)**

Replace DEFAULT_CSS:

```python
    DEFAULT_CSS = """
    ErrorMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    """
```

Replace the __init__ body (lines 488-491):

```python
        text = Text("✗ ", style="#ef4444")
        text.append(error, style="#ef4444")
        super().__init__(text, **kwargs)
```

**Step 7: Restyle SystemMessage (lines 497-505 DEFAULT_CSS)**

Replace DEFAULT_CSS:

```python
    DEFAULT_CSS = """
    SystemMessage {
        height: auto;
        padding: 0 1;
        margin: 1 0;
        color: #3f3f46;
    }
    """
```

Update __init__ (line 515) — use ghost gray instead of dim italic:

```python
        super().__init__(Text(message, style="#3f3f46"), **kwargs)
```

**Step 8: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.messages import UserMessage, AssistantMessage, ToolCallMessage, ErrorMessage, SystemMessage; print('OK')"`
Expected: `OK`

**Step 9: Commit**

```bash
git add src/deepagents_cli/widgets/messages.py
git commit -m "style: restyle all message widgets with Ghost Glass theme"
```

---

### Task 6: Restyle ApprovalMenu — Raised Card

**Files:**
- Modify: `src/deepagents_cli/widgets/approval.py:86-112` (compose method)

**Step 1: Update compose() title and help text**

Replace line 87-89 (title):

```python
        yield Static(
            f"[#e4e4e7]{self._tool_name}[/#e4e4e7] [#71717a]requires approval[/#71717a]",
            classes="approval-title",
        )
```

Replace lines 109-112 (help text):

```python
        yield Static(
            "↑/↓ navigate · enter select · y/n/a",
            classes="approval-help",
        )
```

**Step 2: Update _update_options() styling (lines 135-150)**

Replace lines 135-150:

```python
    def _update_options(self) -> None:
        """Update option widgets based on selection."""
        options = [
            "1. approve (y)",
            "2. reject (n)",
            "3. auto-approve all (a)",
        ]

        for i, (text, widget) in enumerate(zip(options, self._option_widgets, strict=True)):
            cursor = "› " if i == self._selected else "  "
            widget.update(f"{cursor}{text}")

            widget.remove_class("approval-option-selected")
            if i == self._selected:
                widget.add_class("approval-option-selected")
```

**Step 3: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.approval import ApprovalMenu; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/deepagents_cli/widgets/approval.py
git commit -m "style: restyle approval menu with raised card design"
```

---

### Task 7: Restyle ChatInput — Invisible Input

**Files:**
- Modify: `src/deepagents_cli/widgets/chat_input.py:234-270` (DEFAULT_CSS)

**Step 1: Replace ChatInput DEFAULT_CSS**

Replace lines 234-270:

```python
    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 3;
        max-height: 12;
        padding: 0;
        background: #09090b;
    }

    ChatInput .input-row {
        height: auto;
        width: 100%;
    }

    ChatInput .input-prompt {
        width: 3;
        height: 1;
        padding: 0 1;
        color: #3f3f46;
    }

    ChatInput ChatTextArea {
        width: 1fr;
        height: auto;
        min-height: 1;
        max-height: 8;
        border: none;
        background: transparent;
        padding: 0;
        color: #e4e4e7;
    }

    ChatInput ChatTextArea:focus {
        border: none;
    }
    """
```

**Step 2: Add accent prompt when agent is idle**

We need the `>` prompt to turn accent blue (`#00AEEF`) when the agent is idle/ready. Add a method and update `set_cursor_active`:

In `ChatInput`, add after `set_cursor_active` (around line 491):

```python
    def set_prompt_active(self, *, active: bool) -> None:
        """Set the prompt color — accent when idle/ready, ghost when agent is running."""
        try:
            prompt = self.query_one("#prompt", Static)
        except Exception:
            return
        if active:
            prompt.styles.color = "#00AEEF"
        else:
            prompt.styles.color = "#3f3f46"
```

Then in `app.py`, update `_cleanup_agent_task` (around line 1118) to call `set_prompt_active(active=True)` and `_handle_user_message` (around line 1073) to call `set_prompt_active(active=False)`.

In `app.py:_cleanup_agent_task` after `self._chat_input.set_submit_enabled(enabled=True)`:

```python
            self._chat_input.set_prompt_active(active=True)
```

In `app.py:_handle_user_message` after `self._chat_input.set_submit_enabled(enabled=False)`:

```python
                self._chat_input.set_prompt_active(active=False)
```

Also in `app.py:on_mount` after `self._chat_input.focus_input()` (line 366):

```python
        self._chat_input.set_prompt_active(active=True)
```

**Step 3: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.chat_input import ChatInput; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/deepagents_cli/widgets/chat_input.py src/deepagents_cli/app.py
git commit -m "style: invisible input, accent prompt when idle"
```

---

### Task 8: Restyle Diff Rendering — Desaturated

**Files:**
- Modify: `src/deepagents_cli/widgets/diff.py:28-114` (format_diff_textual function)
- Modify: `src/deepagents_cli/widgets/diff.py:120-142` (EnhancedDiff DEFAULT_CSS)
- Modify: `src/deepagents_cli/widgets/diff.py:182` (diff title)

**Step 1: Update format_diff_textual colors**

In `format_diff_textual`, replace the stat colors (lines 59-61):

```python
    if additions:
        stats_parts.append(f"[#4ade80]+{additions}[/#4ade80]")
    if deletions:
        stats_parts.append(f"[#f87171]-{deletions}[/#f87171]")
```

Replace the diff line rendering (lines 87-112):

```python
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
```

**Step 2: Update EnhancedDiff DEFAULT_CSS (lines 120-142)**

Replace with:

```python
    DEFAULT_CSS = """
    EnhancedDiff {
        height: auto;
        padding: 1;
        background: #0f0f11;
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
```

**Step 3: Update diff title markup (line 182)**

Replace:
```python
        yield Static(f"[bold cyan]═══ {self._title} ═══[/bold cyan]", classes="diff-title")
```
With:
```python
        yield Static(f"[#71717a]{self._title}[/#71717a]", classes="diff-title")
```

**Step 4: Update diff stats in compose (lines 191-193)**

Replace:
```python
            if additions:
                stats_parts.append(f"[#00AEEF]+{additions}[/#00AEEF]")
            if deletions:
                stats_parts.append(f"[red]-{deletions}[/red]")
```
With:
```python
            if additions:
                stats_parts.append(f"[#4ade80]+{additions}[/#4ade80]")
            if deletions:
                stats_parts.append(f"[#f87171]-{deletions}[/#f87171]")
```

**Step 5: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.diff import format_diff_textual, EnhancedDiff; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add src/deepagents_cli/widgets/diff.py
git commit -m "style: desaturated diffs, no backgrounds, text-only colors"
```

---

### Task 9: Restyle Tool Widgets — Desaturated Diffs in Approval

**Files:**
- Modify: `src/deepagents_cli/widgets/tool_widgets.py`

**Step 1: Update EditFileApprovalWidget colors**

In `_format_stats` (lines 124-131), replace:
```python
        if additions:
            parts.append(f"[#00AEEF]+{additions}[/#00AEEF]")
        if deletions:
            parts.append(f"[red]-{deletions}[/red]")
```
With:
```python
        if additions:
            parts.append(f"[#4ade80]+{additions}[/#4ade80]")
        if deletions:
            parts.append(f"[#f87171]-{deletions}[/#f87171]")
```

In `_render_diff_line` (lines 161-173), replace the colored backgrounds:

```python
    def _render_diff_line(self, line: str) -> Static | None:
        """Render a single diff line with appropriate styling."""
        content = _escape_markup(line[1:] if len(line) > 1 else "")

        if line.startswith("-"):
            return Static(f"[#f87171]- {content}[/#f87171]")
        if line.startswith("+"):
            return Static(f"[#4ade80]+ {content}[/#4ade80]")
        if line.startswith(" "):
            return Static(f"[#3f3f46]  {content}[/#3f3f46]")
        if line.strip():
            return Static(line, markup=False)
        return None
```

In `_render_string_lines` (lines 175-187), replace colored backgrounds:

```python
    def _render_string_lines(self, text: str, *, is_addition: bool) -> ComposeResult:
        """Render lines from a string with appropriate styling."""
        lines = text.split("\n")
        color = "#4ade80" if is_addition else "#f87171"
        prefix = "+" if is_addition else "-"

        for line in lines[:_MAX_PREVIEW_LINES]:
            escaped = _escape_markup(line)
            yield Static(f"[{color}]{prefix} {escaped}[/{color}]")

        if len(lines) > _MAX_PREVIEW_LINES:
            remaining = len(lines) - _MAX_PREVIEW_LINES
            yield Static(f"[#3f3f46]... ({remaining} more lines)[/#3f3f46]")
```

Update `_render_strings_only` (lines 150-159):

```python
    def _render_strings_only(self, old_string: str, new_string: str) -> ComposeResult:
        """Render old/new strings without returning stats."""
        if old_string:
            yield Static("[#71717a]Removing:[/#71717a]")
            yield from self._render_string_lines(old_string, is_addition=False)
            yield Static("")

        if new_string:
            yield Static("[#71717a]Adding:[/#71717a]")
            yield from self._render_string_lines(new_string, is_addition=True)
```

Update file header in `_render_diff_lines_only` stat line (line 95):

```python
        yield Static(f"[#e4e4e7]File:[/#e4e4e7] {file_path}  {stats_str}")
```

Update FastApplyApprovalWidget (lines 199-200):

```python
        yield Static(f"[#e4e4e7]File:[/#e4e4e7] {file_path}")
        yield Static(f"[#71717a]Model:[/#71717a] {model}")
```

**Step 2: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.tool_widgets import EditFileApprovalWidget, WriteFileApprovalWidget; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/deepagents_cli/widgets/tool_widgets.py
git commit -m "style: desaturated diffs in approval widgets, no backgrounds"
```

---

### Task 10: Restyle Model Selector — Ghost Modal

**Files:**
- Modify: `src/deepagents_cli/widgets/model_selector.py:62-72` (compose)
- Modify: `src/deepagents_cli/widgets/model_selector.py:78-93` (_format_entry)

The CSS is already handled in Task 1 (app.tcss). Here we update the inline markup.

**Step 1: Update compose() title and help**

Replace lines 62-72:

```python
    def compose(self) -> ComposeResult:
        with Container(id="model-selector-panel"):
            yield Static("select model", id="model-selector-title")
            self._search_widget = Static("", id="model-selector-search")
            yield self._search_widget
            self._scroll = VerticalScroll(id="model-selector-scroll")
            self._list_container = self._scroll
            yield self._scroll
            self._help_widget = Static(
                "type to search · enter select · esc cancel · f favorite",
                id="model-selector-help",
            )
            yield self._help_widget
```

**Step 2: Update _format_entry to show (active) in ghost text**

Replace lines 89-92:

```python
        if self._current_model_key and key == self._current_model_key:
            suffix_parts.append("active")
```

No other changes needed — the favorites star `★` already works, CSS handles the rest.

**Step 3: Update help widget status text in action_toggle_favorite (lines 262-264)**

Replace:
```python
            self._help_widget.update(f"{status} • Type to search • Enter select • Esc cancel • F favorite")
```
With:
```python
            self._help_widget.update(f"{status} · type to search · enter select · esc cancel · f favorite")
```

**Step 4: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.widgets.model_selector import ModelSelectorScreen; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/deepagents_cli/widgets/model_selector.py
git commit -m "style: ghost modal for model selector"
```

---

### Task 11: UX Tweak — Model Name Truncation

**Files:**
- Modify: `src/deepagents_cli/app.py:679-681` (display_name in _switch_model)

**Step 1: Add model name truncation helper**

Add after `_strip_model_prefix` (around line 581):

```python
    @staticmethod
    def _truncate_model_name(name: str) -> str:
        """Truncate model name to last meaningful segment.

        E.g. 'claude-opus-4-6' -> 'opus-4-6', 'gpt-4o-mini' -> 'gpt-4o-mini'
        """
        value = name.strip()
        # Strip common provider prefixes
        for prefix in ("claude-", "models/"):
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        return value
```

**Step 2: Use it in _switch_model**

Replace line 679:
```python
        display_name = entry.display_name if entry else (settings.model_name or normalized)
```
With:
```python
        raw_name = entry.display_name if entry else (settings.model_name or normalized)
        display_name = self._truncate_model_name(raw_name)
```

**Step 3: Verify**

Run: `cd /Users/ava/main/deep && python -c "from deepagents_cli.app import DeepAgentsApp; print(DeepAgentsApp._truncate_model_name('claude-opus-4-6'))"`
Expected: `opus-4-6`

**Step 4: Commit**

```bash
git add src/deepagents_cli/app.py
git commit -m "ux: truncate model name to last segment in status bar"
```

---

### Task 12: Final Verification & Cleanup

**Step 1: Run full import check**

```bash
cd /Users/ava/main/deep && python -c "
from deepagents_cli.app import DeepAgentsApp
from deepagents_cli.widgets.status import StatusBar
from deepagents_cli.widgets.welcome import WelcomeBanner
from deepagents_cli.widgets.loading import LoadingWidget
from deepagents_cli.widgets.messages import UserMessage, AssistantMessage, ToolCallMessage, ErrorMessage, SystemMessage
from deepagents_cli.widgets.approval import ApprovalMenu
from deepagents_cli.widgets.chat_input import ChatInput
from deepagents_cli.widgets.model_selector import ModelSelectorScreen
from deepagents_cli.widgets.diff import format_diff_textual, EnhancedDiff
from deepagents_cli.widgets.tool_widgets import EditFileApprovalWidget, WriteFileApprovalWidget
print('All imports OK')
"
```
Expected: `All imports OK`

**Step 2: Run the app to visually verify**

```bash
cd /Users/ava/main/deep && python -m deepagents_cli
```

Verify:
- Background is true black (#09090b)
- Welcome banner: "deepagents ready" in minimal text, no ASCII art
- Input prompt `>` is accent blue when idle
- Status bar is a ghost whisper with dot separators
- No colored borders anywhere

**Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "style: Ghost Glass TUI redesign complete"
```
