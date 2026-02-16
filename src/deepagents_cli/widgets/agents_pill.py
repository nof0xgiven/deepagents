"""Agents pill widget — shows count of running background agents."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class AgentsPill(Static):
    """Subtle pill that shows the number of running background agents.

    Hidden when count is 0. Pulses gently while agents are active.
    """

    DEFAULT_CSS = """
    AgentsPill {
        display: none;
        height: 1;
        width: auto;
        padding: 0 1;
        margin: 0 0 0 1;
        color: #d7e4f0;
        text-style: dim;
    }

    AgentsPill.active {
        display: block;
    }

    AgentsPill.pulse-on {
        color: #f4f8fc;
        text-style: none;
    }
    """

    count: reactive[int] = reactive(0, init=False)

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._pulse_timer = None

    def on_mount(self) -> None:
        self._pulse_timer = self.set_interval(1.2, self._toggle_pulse, pause=True)

    def _toggle_pulse(self) -> None:
        if self.has_class("pulse-on"):
            self.remove_class("pulse-on")
        else:
            self.add_class("pulse-on")

    def watch_count(self, count: int) -> None:
        if count > 0:
            label = f"agents {count} running"
            self.update(label)
            self.add_class("active")
            if self._pulse_timer:
                self._pulse_timer.resume()
        else:
            self.update("")
            self.remove_class("active", "pulse-on")
            if self._pulse_timer:
                self._pulse_timer.pause()

    def increment(self) -> None:
        self.count += 1

    def decrement(self) -> None:
        self.count = max(0, self.count - 1)
