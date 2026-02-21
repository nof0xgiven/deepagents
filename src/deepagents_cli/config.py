"""Configuration, constants, and model creation for the CLI."""

import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dotenv
from rich.console import Console

from deepagents_cli._version import __version__
from deepagents_cli.auth_store import AuthError, AuthStore
from deepagents_cli.model_registry import ModelCatalog, load_model_catalog, resolve_model_query
from deepagents_cli.model_types import ModelEntry, ProviderConfig
from deepagents_cli.provider_adapters import ProviderError, create_chat_model
from deepagents_cli.settings_store import SettingsStore

_deepagents_env = Path.home() / ".deepagents" / ".env"
if _deepagents_env.exists():
    dotenv.load_dotenv(dotenv_path=_deepagents_env, override=False)
dotenv.load_dotenv()

# CRITICAL: Override LANGSMITH_PROJECT to route agent traces to separate project
# LangSmith reads LANGSMITH_PROJECT at invocation time, so we override it here
# and preserve the user's original value for shell commands
_deepagents_project = os.environ.get("DEEPAGENTS_LANGSMITH_PROJECT")
_original_langsmith_project = os.environ.get("LANGSMITH_PROJECT")
if _deepagents_project:
    # Override LANGSMITH_PROJECT for agent traces
    os.environ["LANGSMITH_PROJECT"] = _deepagents_project

# Now safe to import LangChain modules
from langchain_core.language_models import BaseChatModel  # noqa: E402

# Color scheme
COLORS = {
    "primary": "#00AEEF",
    "dim": "#6b7280",
    "user": "#ffffff",
    "agent": "#00AEEF",
    "thinking": "#33CCFF",
    "tool": "#fbbf24",
}

# ASCII art banner

DEEP_AGENTS_ASCII = f"""
 _| _ _ _  _  _  _ _ |_ _ 
(_|(-(-|_)(_|(_)(-| )|__) 
       |     _/            v{__version__}
"""

# Interactive commands
COMMANDS = {
    "assemble": "Assemble Linear issue workflow",
    "model": "Select or switch the active model",
    "models": "List or search models",
    "clear": "Clear screen and reset conversation",
    "help": "Show help information",
    "remember": "Review conversation and update memory/skills",
    "tokens": "Show token usage for current session",
    "quit": "Exit the CLI",
    "exit": "Exit the CLI",
}


# Maximum argument length for display
MAX_ARG_LENGTH = 150

# Agent configuration
config = {"recursion_limit": 1000}

# Rich console instance
console = Console(highlight=False)


def _find_project_root(start_path: Path | None = None) -> Path | None:
    """Find the project root by looking for .git directory.

    Walks up the directory tree from start_path (or cwd) looking for a .git
    directory, which indicates the project root.

    Args:
        start_path: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to the project root if found, None otherwise.
    """
    current = Path(start_path or Path.cwd()).resolve()

    # Walk up the directory tree
    for parent in [current, *list(current.parents)]:
        git_dir = parent / ".git"
        if git_dir.exists():
            return parent

    return None


def _find_project_agent_md(project_root: Path) -> list[Path]:
    """Find project-specific AGENTS.md file(s).

    Checks two locations and returns ALL that exist:
    1. project_root/.deepagents/AGENTS.md
    2. project_root/AGENTS.md

    Both files will be loaded and combined if both exist.

    Args:
        project_root: Path to the project root directory.

    Returns:
        List of paths to project AGENTS.md files (may contain 0, 1, or 2 paths).
    """
    paths = []

    # Check .deepagents/AGENTS.md (preferred)
    deepagents_md = project_root / ".deepagents" / "AGENTS.md"
    if deepagents_md.exists():
        paths.append(deepagents_md)

    # Check root AGENTS.md (fallback, but also include if both exist)
    root_md = project_root / "AGENTS.md"
    if root_md.exists():
        paths.append(root_md)

    return paths


@dataclass
class Settings:
    """Global settings and environment detection for deepagents-cli.

    This class is initialized once at startup and provides access to:
    - Available models and API keys
    - Current project information
    - Tool availability (e.g., Tavily)
    - File system paths

    Attributes:
        project_root: Current project root directory (if in a git project)

        openai_api_key: OpenAI API key if available
        anthropic_api_key: Anthropic API key if available
        tavily_api_key: Tavily API key if available
        deepagents_langchain_project: LangSmith project name for deepagents agent tracing
        user_langchain_project: Original LANGSMITH_PROJECT from environment (for user code)
    """

    # API keys
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    tavily_api_key: str | None

    # LangSmith configuration
    deepagents_langchain_project: str | None  # For deepagents agent tracing
    user_langchain_project: str | None  # Original LANGSMITH_PROJECT for user code

    # Model configuration
    model_name: str | None = None  # Currently active model name
    model_provider: str | None = None  # Provider (openai, anthropic, google)

    # Project information
    project_root: Path | None = None

    @classmethod
    def from_environment(cls, *, start_path: Path | None = None) -> "Settings":
        """Create settings by detecting the current environment.

        Args:
            start_path: Directory to start project detection from (defaults to cwd)

        Returns:
            Settings instance with detected configuration
        """
        # Detect API keys
        openai_key = os.environ.get("OPENAI_API_KEY")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        google_key = os.environ.get("GOOGLE_API_KEY")
        tavily_key = os.environ.get("TAVILY_API_KEY")

        # Detect LangSmith configuration
        # DEEPAGENTS_LANGSMITH_PROJECT: Project for deepagents agent tracing
        # user_langchain_project: User's ORIGINAL LANGSMITH_PROJECT (before override)
        # Note: LANGSMITH_PROJECT was already overridden at module import time (above)
        # so we use the saved original value, not the current os.environ value
        deepagents_langchain_project = os.environ.get("DEEPAGENTS_LANGSMITH_PROJECT")
        user_langchain_project = _original_langsmith_project  # Use saved original!

        # Detect project
        project_root = _find_project_root(start_path)

        return cls(
            openai_api_key=openai_key,
            anthropic_api_key=anthropic_key,
            google_api_key=google_key,
            tavily_api_key=tavily_key,
            deepagents_langchain_project=deepagents_langchain_project,
            user_langchain_project=user_langchain_project,
            project_root=project_root,
        )

    @property
    def has_openai(self) -> bool:
        """Check if OpenAI API key is configured."""
        return self.openai_api_key is not None

    @property
    def has_anthropic(self) -> bool:
        """Check if Anthropic API key is configured."""
        return self.anthropic_api_key is not None

    @property
    def has_google(self) -> bool:
        """Check if Google API key is configured."""
        return self.google_api_key is not None

    @property
    def has_tavily(self) -> bool:
        """Check if Tavily API key is configured."""
        return self.tavily_api_key is not None

    @property
    def has_deepagents_langchain_project(self) -> bool:
        """Check if deepagents LangChain project name is configured."""
        return self.deepagents_langchain_project is not None

    @property
    def has_project(self) -> bool:
        """Check if currently in a git project."""
        return self.project_root is not None

    @property
    def user_deepagents_dir(self) -> Path:
        """Get the base user-level .deepagents directory.

        Returns:
            Path to ~/.deepagents
        """
        return Path.home() / ".deepagents"

    @property
    def user_agents_dir(self) -> Path:
        """Get the base user-level .agents directory.

        Returns:
            Path to ~/.agents
        """
        return Path.home() / ".agents"

    def get_user_agent_md_path(self, agent_name: str) -> Path:
        """Get user-level AGENTS.md path for a specific agent.

        Returns path regardless of whether the file exists.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ~/.deepagents/{agent_name}/AGENTS.md
        """
        return Path.home() / ".deepagents" / agent_name / "AGENTS.md"

    def get_user_system_md_path(self, assistant_id: str) -> Path | None:
        """Return user-level SYSTEM.md path if it exists.

        Args:
            assistant_id: The agent identifier

        Returns:
            Path to ~/.deepagents/{assistant_id}/SYSTEM.md if it exists, None otherwise.
        """
        path = self.user_deepagents_dir / assistant_id / "SYSTEM.md"
        if path.exists():
            return path
        path_lower = self.user_deepagents_dir / assistant_id / "system.md"
        if path_lower.exists():
            return path_lower
        return None

    def get_project_agent_md_path(self) -> Path | None:
        """Get project-level AGENTS.md path.

        Returns path regardless of whether the file exists.

        Returns:
            Path to {project_root}/.deepagents/AGENTS.md, or None if not in a project
        """
        if not self.project_root:
            return None
        return self.project_root / ".deepagents" / "AGENTS.md"

    @staticmethod
    def _is_valid_agent_name(agent_name: str) -> bool:
        """Validate prevent invalid filesystem paths and security issues."""
        if not agent_name or not agent_name.strip():
            return False
        # Allow only alphanumeric, hyphens, underscores, and whitespace
        return bool(re.match(r"^[a-zA-Z0-9_\-\s]+$", agent_name))

    def get_agent_dir(self, agent_name: str) -> Path:
        """Get the global agent directory path.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ~/.deepagents/{agent_name}
        """
        if not self._is_valid_agent_name(agent_name):
            msg = (
                f"Invalid agent name: {agent_name!r}. "
                "Agent names can only contain letters, numbers, hyphens, underscores, and spaces."
            )
            raise ValueError(msg)
        return Path.home() / ".deepagents" / agent_name

    def ensure_agent_dir(self, agent_name: str) -> Path:
        """Ensure the global agent directory exists and return its path.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ~/.deepagents/{agent_name}
        """
        if not self._is_valid_agent_name(agent_name):
            msg = (
                f"Invalid agent name: {agent_name!r}. "
                "Agent names can only contain letters, numbers, hyphens, underscores, and spaces."
            )
            raise ValueError(msg)
        agent_dir = self.get_agent_dir(agent_name)
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir

    def ensure_project_deepagents_dir(self) -> Path | None:
        """Ensure the project .deepagents directory exists and return its path.

        Returns:
            Path to project .deepagents directory, or None if not in a project
        """
        if not self.project_root:
            return None

        project_deepagents_dir = self.project_root / ".deepagents"
        project_deepagents_dir.mkdir(parents=True, exist_ok=True)
        return project_deepagents_dir

    def get_user_skills_dir(self, agent_name: str) -> Path:
        """Get user-level skills directory path for a specific agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ~/.deepagents/{agent_name}/skills/
        """
        return self.get_agent_dir(agent_name) / "skills"

    def ensure_user_skills_dir(self, agent_name: str) -> Path:
        """Ensure user-level skills directory exists and return its path.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ~/.deepagents/{agent_name}/skills/
        """
        skills_dir = self.get_user_skills_dir(agent_name)
        skills_dir.mkdir(parents=True, exist_ok=True)
        return skills_dir

    def get_default_skills_dir(self) -> Path:
        """Get shared default skills directory path.

        Returns:
            Path to ~/.agents/skills/
        """
        return self.user_agents_dir / "skills"

    def get_project_skills_dir(self) -> Path | None:
        """Get project-level skills directory path.

        Returns:
            Path to {project_root}/.deepagents/skills/, or None if not in a project
        """
        if not self.project_root:
            return None
        return self.project_root / ".deepagents" / "skills"

    def ensure_project_skills_dir(self) -> Path | None:
        """Ensure project-level skills directory exists and return its path.

        Returns:
            Path to {project_root}/.deepagents/skills/, or None if not in a project
        """
        if not self.project_root:
            return None
        skills_dir = self.get_project_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        return skills_dir


# Global settings instance (initialized once)
settings = Settings.from_environment()


class SessionState:
    """Holds mutable session state (auto-approve mode, etc)."""

    def __init__(self, auto_approve: bool = True, no_splash: bool = False) -> None:
        self.auto_approve = auto_approve
        self.no_splash = no_splash
        self.exit_hint_until: float | None = None
        self.exit_hint_handle = None
        self.thread_id = str(uuid.uuid4())

    def toggle_auto_approve(self) -> bool:
        """Toggle auto-approve and return new state."""
        self.auto_approve = not self.auto_approve
        return self.auto_approve


def get_default_coding_instructions() -> str:
    """Get the default coding agent instructions.

    These are the immutable base instructions that cannot be modified by the agent.
    Long-term memory (AGENTS.md) is handled separately by the middleware.
    """
    default_prompt_path = Path(__file__).parent / "default_agent_prompt.md"

    project_root = settings.project_root
    if project_root:
        override_candidates = [
            project_root / ".deepagents" / "system.md",
            project_root / ".deepagents" / "SYSTEM.md",
        ]
        for override_path in override_candidates:
            if override_path.exists():
                return override_path.read_text()

    return default_prompt_path.read_text()


def _detect_provider(model_name: str) -> str | None:
    """Auto-detect provider from model name.

    Args:
        model_name: Model name to detect provider from

    Returns:
        Provider name (openai, anthropic, google) or None if can't detect
    """
    model_lower = model_name.lower()
    if any(x in model_lower for x in ["gpt", "o1", "o3"]):
        return "openai"
    if "claude" in model_lower:
        return "anthropic"
    if "gemini" in model_lower:
        return "google"
    return None


REASONING_EFFORT_ALLOWED = {"none", "low", "medium", "high", "xhigh"}


class NoModelSelectedError(RuntimeError):
    pass


class ModelConfigurationError(RuntimeError):
    pass


def _resolve_reasoning_effort(value: str | None, default: str | None) -> str:
    """Normalize reasoning effort and validate allowed values."""
    effort = (value or default or os.environ.get("DEEPAGENTS_REASONING_EFFORT") or "high").strip().lower()
    if effort not in REASONING_EFFORT_ALLOWED:
        console.print(f"[bold red]Error:[/bold red] Invalid reasoning effort: {effort}")
        console.print("Allowed values: none, low, medium, high, xhigh")
        sys.exit(1)
    return effort


def _resolve_service_tier(value: str | None, default: str | None) -> str:
    """Resolve OpenAI service tier with priority default."""
    tier = (value or default or os.environ.get("DEEPAGENTS_SERVICE_TIER") or "priority").strip()
    if tier == "prioty":
        tier = "priority"
    return tier


def _builtin_provider(provider: str) -> ProviderConfig | None:
    name = provider.lower()
    if name == "openai":
        return ProviderConfig(name="openai", api="openai-responses", base_url=None)
    if name == "anthropic":
        return ProviderConfig(name="anthropic", api="anthropic-messages", base_url=None)
    if name == "google":
        return ProviderConfig(name="google", api="google-generative-ai", base_url=None)
    return None


def _entry_from_active(active: dict[str, Any], provider: ProviderConfig) -> ModelEntry:
    model_id = str(active.get("id") or "").strip()
    if not model_id:
        raise ModelConfigurationError("Active model config missing id")
    name = str(active.get("name") or model_id).strip()
    alias = str(active.get("alias") or active.get("name") or model_id).strip()
    api = str(active.get("api") or provider.api).strip()
    base_url = active.get("base_url") or active.get("baseUrl") or provider.base_url
    if isinstance(base_url, str):
        base_url = base_url.strip() or None
    else:
        base_url = None
    reasoning = active.get("reasoning") or active.get("reasoning_effort")
    reasoning_effort = None
    reasoning_enabled = None
    if isinstance(reasoning, bool):
        reasoning_enabled = reasoning
    elif isinstance(reasoning, str):
        val = reasoning.strip().lower()
        if val in {"false", "off", "none", "no"}:
            reasoning_enabled = False
        else:
            reasoning_enabled = True
            reasoning_effort = val
    service_tier = active.get("service_tier") or active.get("serviceTier")
    if isinstance(service_tier, str):
        service_tier = service_tier.strip() or None
    else:
        service_tier = None
    inputs = active.get("input") or active.get("inputs")
    if isinstance(inputs, list):
        inputs = [str(item) for item in inputs if str(item).strip()]
    else:
        inputs = None
    max_tokens = active.get("max_tokens") or active.get("maxTokens")
    if isinstance(max_tokens, str) and max_tokens.isdigit():
        max_tokens = int(max_tokens)
    if not isinstance(max_tokens, int):
        max_tokens = None
    context_window = active.get("context_window") or active.get("contextWindow")
    if isinstance(context_window, str) and context_window.isdigit():
        context_window = int(context_window)
    if not isinstance(context_window, int):
        context_window = None
    compat = active.get("compat")
    if not isinstance(compat, dict):
        compat = {}
    return ModelEntry(
        id=model_id,
        name=name,
        alias=alias or model_id,
        provider=provider.name,
        api=api,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
        reasoning_enabled=reasoning_enabled,
        service_tier=service_tier,
        inputs=inputs,
        max_tokens=max_tokens,
        context_window=context_window,
        compat=compat,
        source=Path("settings"),
    )


def _resolve_model_selection(
    model_name_override: str | None,
    catalog: ModelCatalog,
    settings_store: SettingsStore,
) -> ModelEntry | None:
    if model_name_override:
        exact = resolve_model_query(model_name_override, catalog.models)
        if exact:
            return exact
        if ":" in model_name_override:
            provider_name, model_id = model_name_override.split(":", 1)
            provider_name = provider_name.strip()
            model_id = model_id.strip()
            provider = catalog.providers.get(provider_name) or _builtin_provider(provider_name)
            if not provider:
                raise ModelConfigurationError(f"Provider '{provider_name}' is not configured")
            return _entry_from_active({"id": model_id}, provider)
        detected = _detect_provider(model_name_override)
        if detected:
            provider = catalog.providers.get(detected) or _builtin_provider(detected)
            if provider:
                return _entry_from_active({"id": model_name_override}, provider)
        raise ModelConfigurationError(
            f"Model '{model_name_override}' not found. Add it to ~/.deepagents/models.json or settings.json."
        )

    active = settings_store.get_active_model()
    if isinstance(active, dict):
        provider_name = str(active.get("provider") or "").strip()
        if not provider_name:
            raise ModelConfigurationError("Active model config missing provider")
        provider = catalog.providers.get(provider_name) or _builtin_provider(provider_name)
        if not provider:
            raise ModelConfigurationError(f"Provider '{provider_name}' is not configured")
        return _entry_from_active(active, provider)
    if isinstance(active, str) and active.strip():
        exact = resolve_model_query(active, catalog.models)
        if exact:
            return exact
        if ":" in active:
            provider_name, model_id = active.split(":", 1)
            provider_name = provider_name.strip()
            model_id = model_id.strip()
            provider = catalog.providers.get(provider_name) or _builtin_provider(provider_name)
            if not provider:
                raise ModelConfigurationError(f"Provider '{provider_name}' is not configured")
            return _entry_from_active({"id": model_id}, provider)
        detected = _detect_provider(active)
        if detected:
            provider = catalog.providers.get(detected) or _builtin_provider(detected)
            if provider:
                return _entry_from_active({"id": active}, provider)
        return None
    return None


def create_model(
    model_name_override: str | None = None,
    *,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
) -> BaseChatModel:
    """Create the configured model from catalogs and settings."""
    settings_store = SettingsStore(settings.project_root)
    catalog = load_model_catalog(project_root=settings.project_root)
    entry = _resolve_model_selection(model_name_override, catalog, settings_store)
    if entry is None:
        raise NoModelSelectedError(
            "No active model selected. Use /model to choose one or set model.active in settings.json."
        )
    provider = catalog.providers.get(entry.provider) or _builtin_provider(entry.provider)
    if not provider:
        raise ModelConfigurationError(f"Provider '{entry.provider}' is not configured")

    auth_store = AuthStore()
    try:
        auth = auth_store.resolve(provider.name, provider.auth)
    except AuthError as exc:
        raise ModelConfigurationError(str(exc)) from exc
    if auth is None:
        raise ModelConfigurationError(
            f"No credentials configured for provider '{provider.name}'. Add to ~/.deepagents/auth.json or settings."
        )

    default_reasoning = settings_store.get_default_reasoning()
    default_service_tier = settings_store.get_default_service_tier()

    effective_reasoning: str | None = None
    effective_service_tier: str | None = None

    if entry.api == "openai-responses":
        if entry.reasoning_enabled is False:
            effective_reasoning = "none"
        else:
            effective_reasoning = _resolve_reasoning_effort(
                reasoning_effort or entry.reasoning_effort, default_reasoning
            )
        effective_service_tier = _resolve_service_tier(
            service_tier or entry.service_tier, default_service_tier
        )

    try:
        model = create_chat_model(
            entry,
            provider,
            auth,
            reasoning_effort=effective_reasoning,
            service_tier=effective_service_tier,
        )
    except ProviderError as exc:
        raise ModelConfigurationError(str(exc)) from exc

    settings.model_name = entry.id
    settings.model_provider = entry.provider
    return model
