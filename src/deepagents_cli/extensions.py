"""Extension system for deepagents CLI."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from langchain.agents.middleware.types import AgentMiddleware
from langchain.tools import BaseTool
from langgraph.store.base import BaseStore
from langgraph.runtime import Runtime

from deepagents.backends.protocol import BackendProtocol
from deepagents_cli.config import console, settings

EXTENSION_EVENTS = {
    "session_start",
    "session_end",
    "tool_call",
    "tool_result",
    "agent_response",
}

EventHandler = Callable[[dict[str, Any], "ExtensionEventContext"], Any]


@dataclass(frozen=True)
class ExtensionEventContext:
    """Context passed to extension event handlers."""

    extension_name: str
    config: dict[str, Any]
    assistant_id: str
    project_root: Path | None
    store: BaseStore | None
    backend: BackendProtocol | None
    runtime: Runtime | None


@dataclass(frozen=True)
class ExtensionSpec:
    name: str
    entry_module: str | None
    entry_file: Path | None
    entry_func: str
    base_dir: Path
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HookEntry:
    extension_name: str
    handler: EventHandler
    config: dict[str, Any]


class ExtensionAPI:
    """API exposed to extension entrypoints."""

    def __init__(
        self,
        *,
        name: str,
        manager: "ExtensionManager",
        config: dict[str, Any],
    ) -> None:
        self.name = name
        self._manager = manager
        self._config = config

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def register_tool(self, tool: BaseTool | Callable | dict[str, Any]) -> None:
        self._manager.tools.append(tool)

    def register_middleware(self, middleware: AgentMiddleware) -> None:
        self._manager.middleware.append(middleware)

    def register_subagent(self, spec: dict[str, Any]) -> None:
        self._manager.subagents.append(spec)

    def register_prompt(self, text: str) -> None:
        if text.strip():
            self._manager.prompt_additions.append(text.strip())

    def on(self, event: str, handler: EventHandler) -> None:
        event = event.strip().lower()
        if event not in EXTENSION_EVENTS:
            console.print(f"[yellow]⚠️ Unknown extension event: {event}[/yellow]")
            return
        self._manager.add_hook(event, self.name, handler, self._config)

    def get_store(self) -> BaseStore | None:
        return self._manager.store

    def get_backend(self) -> BackendProtocol | None:
        return self._manager.backend

    def get_project_root(self) -> Path | None:
        return self._manager.project_root


class ExtensionsMiddleware(AgentMiddleware):
    """Dispatches lifecycle events to registered extensions."""

    def __init__(self, manager: "ExtensionManager") -> None:
        self._manager = manager

    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        self._run_hooks_sync("session_start", {"state": state}, runtime)
        return None

    async def abefore_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        await self._run_hooks("session_start", {"state": state}, runtime)
        return None

    def after_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        self._run_hooks_sync("session_end", {"state": state}, runtime)
        return None

    async def aafter_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        await self._run_hooks("session_end", {"state": state}, runtime)
        return None

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        tool_call = getattr(request, "tool_call", {})
        tool_name = getattr(request, "tool", None)
        tool_name = getattr(tool_name, "name", None) or tool_call.get("name")
        event = {"tool_call": tool_call, "tool_name": tool_name}
        self._run_hooks_sync("tool_call", event, getattr(request, "runtime", None))

        result = handler(request)
        result_event = {"tool_call": tool_call, "tool_name": tool_name, "result": result}
        self._run_hooks_sync("tool_result", result_event, getattr(request, "runtime", None))
        return result

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        tool_call = getattr(request, "tool_call", {})
        tool_name = getattr(request, "tool", None)
        tool_name = getattr(tool_name, "name", None) or tool_call.get("name")
        event = {"tool_call": tool_call, "tool_name": tool_name}
        await self._run_hooks("tool_call", event, getattr(request, "runtime", None))

        result = await handler(request)
        result_event = {"tool_call": tool_call, "tool_name": tool_name, "result": result}
        await self._run_hooks("tool_result", result_event, getattr(request, "runtime", None))
        return result

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        response = handler(request)
        event = {"response": response}
        self._run_hooks_sync("agent_response", event, getattr(request, "runtime", None))
        return response

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        response = await handler(request)
        event = {"response": response}
        await self._run_hooks("agent_response", event, getattr(request, "runtime", None))
        return response

    def _run_hooks_sync(self, event: str, payload: dict[str, Any], runtime: Runtime | None) -> None:
        for entry in self._manager.hooks.get(event, []):
            ctx = self._manager.build_event_context(entry, runtime)
            try:
                result = entry.handler(payload, ctx)
                if inspect.isawaitable(result):
                    try:
                        asyncio.run(result)
                    except RuntimeError:
                        console.print(
                            f"[yellow]⚠️ Extension '{entry.extension_name}' async hook "
                            f"ignored in sync context for event {event}.[/yellow]"
                        )
            except Exception as exc:
                console.print(
                    f"[yellow]⚠️ Extension '{entry.extension_name}' hook error ({event}): {exc}[/yellow]"
                )

    async def _run_hooks(self, event: str, payload: dict[str, Any], runtime: Runtime | None) -> None:
        for entry in self._manager.hooks.get(event, []):
            ctx = self._manager.build_event_context(entry, runtime)
            try:
                result = entry.handler(payload, ctx)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                console.print(
                    f"[yellow]⚠️ Extension '{entry.extension_name}' hook error ({event}): {exc}[/yellow]"
                )


class ExtensionManager:
    """Loads and manages extension registrations."""

    def __init__(
        self,
        *,
        assistant_id: str,
        project_root: Path | None,
        store: BaseStore | None,
        backend: BackendProtocol | None,
    ) -> None:
        self.assistant_id = assistant_id
        self.project_root = project_root
        self.store = store
        self.backend = backend
        self.tools: list[BaseTool | Callable | dict[str, Any]] = []
        self.middleware: list[AgentMiddleware] = []
        self.subagents: list[dict[str, Any]] = []
        self.prompt_additions: list[str] = []
        self.hooks: dict[str, list[HookEntry]] = {event: [] for event in EXTENSION_EVENTS}

    def add_hook(
        self, event: str, extension_name: str, handler: EventHandler, config: dict[str, Any]
    ) -> None:
        self.hooks[event].append(
            HookEntry(extension_name=extension_name, handler=handler, config=config)
        )

    def build_event_context(self, entry: HookEntry, runtime: Runtime | None) -> ExtensionEventContext:
        return ExtensionEventContext(
            extension_name=entry.extension_name,
            config=entry.config,
            assistant_id=self.assistant_id,
            project_root=self.project_root,
            store=self.store,
            backend=self.backend,
            runtime=runtime,
        )

    def has_hooks(self) -> bool:
        return any(self.hooks[event] for event in EXTENSION_EVENTS)

    def build_middleware(self) -> ExtensionsMiddleware:
        return ExtensionsMiddleware(self)

    def load_extensions(self, specs: Iterable[ExtensionSpec]) -> None:
        for spec in specs:
            if not spec.enabled:
                continue
            try:
                entrypoint = _load_entrypoint(spec)
                api = ExtensionAPI(name=spec.name, manager=self, config=spec.config)
                result = entrypoint(api)
                if inspect.isawaitable(result):
                    console.print(
                        f"[yellow]⚠️ Extension '{spec.name}' register returned an awaitable; async registration is not supported.[/yellow]"
                    )
            except Exception as exc:
                console.print(
                    f"[yellow]⚠️ Failed to load extension '{spec.name}': {exc}[/yellow]"
                )


def load_extensions(
    *,
    assistant_id: str,
    project_root: Path | None,
    store: BaseStore | None,
    backend: BackendProtocol | None,
    explicit: list[str] | None = None,
    only_explicit: bool = False,
    disabled: bool = False,
) -> ExtensionManager:
    manager = ExtensionManager(
        assistant_id=assistant_id,
        project_root=project_root,
        store=store,
        backend=backend,
    )

    if disabled:
        return manager

    specs = _discover_extensions(
        project_root=project_root,
        explicit=explicit or [],
        only_explicit=only_explicit,
    )
    manager.load_extensions(specs)
    return manager


def _read_settings() -> dict[str, Any]:
    settings_path = Path.home() / ".deepagents" / "settings.json"
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text())
    except Exception as exc:
        console.print(f"[yellow]⚠️ Failed to parse {settings_path}: {exc}[/yellow]")
        return {}


def _discover_extensions(
    *, project_root: Path | None, explicit: list[str], only_explicit: bool
) -> list[ExtensionSpec]:
    specs_by_name: dict[str, ExtensionSpec] = {}
    settings_data = _read_settings()
    settings_extensions = settings_data.get("extensions", [])
    settings_overrides = settings_data.get("extension_settings", {})

    def add_spec(spec: ExtensionSpec) -> None:
        specs_by_name[spec.name] = spec

    if not only_explicit:
        user_dir = settings.user_deepagents_dir / "extensions"
        add_specs_from_dir(user_dir, add_spec, settings_overrides)
        if project_root:
            project_dir = project_root / ".deepagents" / "extensions"
            add_specs_from_dir(project_dir, add_spec, settings_overrides)

    add_specs_from_explicit(settings_extensions, add_spec, settings_overrides)
    add_specs_from_explicit(explicit, add_spec, settings_overrides)

    return list(specs_by_name.values())


def add_specs_from_explicit(
    entries: Iterable[Any],
    add_spec: Callable[[ExtensionSpec], None],
    settings_overrides: dict[str, Any],
) -> None:
    for entry in entries:
        spec = _spec_from_entry(entry, settings_overrides)
        if spec:
            add_spec(spec)


def add_specs_from_dir(
    root: Path,
    add_spec: Callable[[ExtensionSpec], None],
    settings_overrides: dict[str, Any],
) -> None:
    if not root.exists():
        return
    for item in sorted(root.iterdir()):
        if item.name.startswith("."):
            continue
        spec = _spec_from_path(item, settings_overrides)
        if spec:
            add_spec(spec)


def _spec_from_entry(entry: Any, settings_overrides: dict[str, Any]) -> ExtensionSpec | None:
    if isinstance(entry, str):
        path = Path(os.path.expanduser(entry))
        if path.exists():
            return _spec_from_path(path, settings_overrides)
        module_spec = _spec_from_module_string(entry, settings_overrides)
        if module_spec:
            return module_spec
        console.print(f"[yellow]⚠️ Extension entry not found: {entry}[/yellow]")
        return None
    if isinstance(entry, dict):
        path_value = entry.get("path") or entry.get("entry")
        if not path_value:
            return None
        path = Path(os.path.expanduser(str(path_value)))
        spec = _spec_from_path(path, settings_overrides)
        if spec:
            enabled = entry.get("enabled", True)
            config = entry.get("config") or {}
            merged_config = _merge_config(spec.name, settings_overrides, config)
            return ExtensionSpec(
                name=spec.name,
                entry_module=spec.entry_module,
                entry_file=spec.entry_file,
                entry_func=spec.entry_func,
                base_dir=spec.base_dir,
                enabled=bool(enabled),
                config=merged_config,
            )
        return None
    return None


def _spec_from_path(path: Path, settings_overrides: dict[str, Any]) -> ExtensionSpec | None:
    if path.is_file() and path.suffix == ".py":
        name = path.stem
        config = _merge_config(name, settings_overrides, {})
        return ExtensionSpec(
            name=name,
            entry_module=None,
            entry_file=path,
            entry_func="register",
            base_dir=path.parent,
            config=config,
        )
    if path.is_dir():
        manifest = path / "extension.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
            except Exception as exc:
                console.print(f"[yellow]⚠️ Failed to parse {manifest}: {exc}[/yellow]")
                return None
            name = str(data.get("name") or path.name)
            entrypoint = data.get("entrypoint")
            if not entrypoint:
                console.print(
                    f"[yellow]⚠️ Missing entrypoint in {manifest} for {name}[/yellow]"
                )
                return None
            enabled = bool(data.get("enabled", True))
            spec = _spec_from_entrypoint(entrypoint, base_dir=path, name=name)
            if spec is None:
                return None
            inline_config = data.get("config") if isinstance(data.get("config"), dict) else {}
            config = _merge_config(name, settings_overrides, inline_config)
            return ExtensionSpec(
                name=spec.name,
                entry_module=spec.entry_module,
                entry_file=spec.entry_file,
                entry_func=spec.entry_func,
                base_dir=spec.base_dir,
                enabled=enabled,
                config=config,
            )
        index_file = path / "index.py"
        if index_file.exists():
            name = path.name
            config = _merge_config(name, settings_overrides, {})
            return ExtensionSpec(
                name=name,
                entry_module=None,
                entry_file=index_file,
                entry_func="register",
                base_dir=path,
                config=config,
            )
    return None


def _spec_from_module_string(
    value: str, settings_overrides: dict[str, Any]
) -> ExtensionSpec | None:
    if ":" not in value:
        return None
    module_name, func = value.split(":", 1)
    name = module_name.split(".")[-1]
    config = _merge_config(name, settings_overrides, {})
    return ExtensionSpec(
        name=name,
        entry_module=module_name,
        entry_file=None,
        entry_func=func,
        base_dir=Path.cwd(),
        config=config,
    )


def _spec_from_entrypoint(
    entrypoint: str, base_dir: Path, name: str
) -> ExtensionSpec | None:
    if ":" not in entrypoint:
        console.print(f"[yellow]⚠️ Invalid extension entrypoint: {entrypoint}[/yellow]")
        return None
    module_part, func = entrypoint.split(":", 1)
    module_part = module_part.strip()
    func = func.strip()
    if not func:
        console.print(f"[yellow]⚠️ Invalid extension entrypoint: {entrypoint}[/yellow]")
        return None

    if module_part.endswith(".py") or "/" in module_part or module_part.startswith("."):
        module_path = (base_dir / module_part).resolve()
        return ExtensionSpec(
            name=name,
            entry_module=None,
            entry_file=module_path,
            entry_func=func,
            base_dir=base_dir,
        )

    return ExtensionSpec(
        name=name,
        entry_module=module_part,
        entry_file=None,
        entry_func=func,
        base_dir=base_dir,
    )


def _merge_config(
    name: str, settings_overrides: dict[str, Any], inline_config: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(settings_overrides, dict) and name in settings_overrides:
        override = settings_overrides.get(name)
        if isinstance(override, dict):
            merged.update(override)
    if inline_config:
        merged.update(inline_config)
    return merged


def _load_entrypoint(spec: ExtensionSpec) -> Callable[[ExtensionAPI], None]:
    if spec.entry_file is not None:
        module = _load_module_from_file(spec.entry_file, spec.name, spec.base_dir)
    elif spec.entry_module is not None:
        _ensure_on_syspath(spec.base_dir)
        module = importlib.import_module(spec.entry_module)
    else:
        raise ValueError(f"Extension {spec.name} has no entrypoint")

    func = getattr(module, spec.entry_func, None)
    if not callable(func):
        raise ValueError(f"Extension {spec.name} entrypoint missing: {spec.entry_func}")
    return func


def _ensure_on_syspath(path: Path) -> None:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_module_from_file(path: Path, name: str, base_dir: Path) -> Any:
    _ensure_on_syspath(base_dir)
    module_name = f"deepagents_ext_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load extension module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
