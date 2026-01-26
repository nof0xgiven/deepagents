"""MCP (Model Context Protocol) tool integrations."""

from __future__ import annotations

import os
import shlex
import shutil
from contextlib import AsyncExitStack, asynccontextmanager

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection
from langchain_mcp_adapters.tools import load_mcp_tools

from deepagents_cli.config import console


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _chrome_mcp_enabled() -> bool:
    return _env_flag("DEEPAGENTS_MCP", default=True) and _env_flag(
        "DEEPAGENTS_CHROME_MCP", default=True
    )


def _build_chrome_devtools_connection() -> StdioConnection | None:
    if not _chrome_mcp_enabled():
        return None

    command = os.environ.get("DEEPAGENTS_CHROME_MCP_COMMAND", "npx").strip()
    if not command:
        console.print("[yellow]⚠️ Chrome DevTools MCP disabled: empty command[/yellow]")
        return None

    if shutil.which(command) is None:
        console.print(
            "[yellow]⚠️ Chrome DevTools MCP disabled: command not found:[/yellow] "
            f"{command}"
        )
        return None

    package = os.environ.get(
        "DEEPAGENTS_CHROME_MCP_PACKAGE", "chrome-devtools-mcp@latest"
    ).strip()
    if not package:
        console.print("[yellow]⚠️ Chrome DevTools MCP disabled: empty package[/yellow]")
        return None

    args: list[str] = ["-y", package]

    browser_url = os.environ.get("DEEPAGENTS_CHROME_BROWSER_URL")
    ws_endpoint = os.environ.get("DEEPAGENTS_CHROME_WS_ENDPOINT")
    auto_connect = _env_flag("DEEPAGENTS_CHROME_AUTOCONNECT", default=True)
    channel = os.environ.get("DEEPAGENTS_CHROME_CHANNEL")

    if browser_url and ws_endpoint:
        console.print(
            "[yellow]⚠️ Both DEEPAGENTS_CHROME_BROWSER_URL and "
            "DEEPAGENTS_CHROME_WS_ENDPOINT set; using ws endpoint.[/yellow]"
        )
        browser_url = None

    if (browser_url or ws_endpoint) and auto_connect:
        console.print(
            "[yellow]⚠️ DEEPAGENTS_CHROME_AUTOCONNECT ignored because a "
            "browser URL or WS endpoint was provided.[/yellow]"
        )
        auto_connect = False

    if browser_url:
        args.append(f"--browser-url={browser_url}")

    if ws_endpoint:
        args.append(f"--wsEndpoint={ws_endpoint}")

    if auto_connect:
        args.append("--autoConnect")
        if channel:
            args.append(f"--channel={channel}")
    elif channel:
        console.print(
            "[yellow]⚠️ DEEPAGENTS_CHROME_CHANNEL ignored without "
            "DEEPAGENTS_CHROME_AUTOCONNECT.[/yellow]"
        )

    extra_args = os.environ.get("DEEPAGENTS_CHROME_MCP_ARGS")
    if extra_args:
        try:
            args.extend(shlex.split(extra_args))
        except ValueError as exc:
            console.print(
                f"[yellow]⚠️ Ignoring DEEPAGENTS_CHROME_MCP_ARGS: {exc}[/yellow]"
            )

    return {
        "transport": "stdio",
        "command": command,
        "args": args,
    }


@asynccontextmanager
async def open_mcp_tools() -> list[BaseTool]:
    """Return MCP tools with sessions kept open for the app lifecycle."""
    connections: dict[str, StdioConnection] = {}

    chrome_connection = _build_chrome_devtools_connection()
    if chrome_connection:
        connections["chrome"] = chrome_connection

    if not connections:
        yield []
        return

    client = MultiServerMCPClient(connections)
    async with AsyncExitStack() as stack:
        tools: list[BaseTool] = []
        for name in connections:
            try:
                session = await stack.enter_async_context(client.session(name))
                server_tools = await load_mcp_tools(
                    session,
                    server_name=name,
                    tool_name_prefix=True,
                )
                tools.extend(server_tools)
            except Exception as exc:
                console.print(
                    f"[yellow]⚠️ MCP server '{name}' unavailable:[/yellow] {exc}"
                )
        yield tools
