"""Custom tools for the CLI agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import os
import re
import shutil
import subprocess

import requests
from markdownify import markdownify
from tavily import TavilyClient

from deepagents_cli.config import settings

# Initialize Tavily client if API key is available
tavily_client = TavilyClient(api_key=settings.tavily_api_key) if settings.has_tavily else None


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: str | dict | None = None,
    params: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Make HTTP requests to APIs and web services.

    Args:
        url: Target URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: HTTP headers to include
        data: Request body data (string or dict)
        params: URL query parameters
        timeout: Request timeout in seconds

    Returns:
        Dictionary with response data including status, headers, and content
    """
    try:
        kwargs = {"url": url, "method": method.upper(), "timeout": timeout}

        if headers:
            kwargs["headers"] = headers
        if params:
            kwargs["params"] = params
        if data:
            if isinstance(data, dict):
                kwargs["json"] = data
            else:
                kwargs["data"] = data

        response = requests.request(**kwargs)

        try:
            content = response.json()
        except:
            content = response.text

        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content": content,
            "url": response.url,
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Request timed out after {timeout} seconds",
            "url": url,
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Request error: {e!s}",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "headers": {},
            "content": f"Error making request: {e!s}",
            "url": url,
        }


def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Search the web using Tavily for current information and documentation.

    This tool searches the web and returns relevant results. After receiving results,
    you MUST synthesize the information into a natural, helpful response for the user.

    Args:
        query: The search query (be specific and detailed)
        max_results: Number of results to return (default: 5)
        topic: Search topic type - "general" for most queries, "news" for current events
        include_raw_content: Include full page content (warning: uses more tokens)

    Returns:
        Dictionary containing:
        - results: List of search results, each with:
            - title: Page title
            - url: Page URL
            - content: Relevant excerpt from the page
            - score: Relevance score (0-1)
        - query: The original search query

    IMPORTANT: After using this tool:
    1. Read through the 'content' field of each result
    2. Extract relevant information that answers the user's question
    3. Synthesize this into a clear, natural language response
    4. Cite sources by mentioning the page titles or URLs
    5. NEVER show the raw JSON to the user - always provide a formatted response
    """
    if tavily_client is None:
        return {
            "error": "Tavily API key not configured. Please set TAVILY_API_KEY environment variable.",
            "query": query,
        }

    try:
        return tavily_client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )
    except Exception as e:
        return {"error": f"Web search error: {e!s}", "query": query}


def fetch_url(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fetch content from a URL and convert HTML to markdown format.

    This tool fetches web page content and converts it to clean markdown text,
    making it easy to read and process HTML content. After receiving the markdown,
    you MUST synthesize the information into a natural, helpful response for the user.

    Args:
        url: The URL to fetch (must be a valid HTTP/HTTPS URL)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary containing:
        - success: Whether the request succeeded
        - url: The final URL after redirects
        - markdown_content: The page content converted to markdown
        - status_code: HTTP status code
        - content_length: Length of the markdown content in characters

    IMPORTANT: After using this tool:
    1. Read through the markdown content
    2. Extract relevant information that answers the user's question
    3. Synthesize this into a clear, natural language response
    4. NEVER show the raw markdown to the user unless specifically requested
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DeepAgents/1.0)"},
        )
        response.raise_for_status()

        # Convert HTML content to markdown
        markdown_content = markdownify(response.text)

        return {
            "url": str(response.url),
            "markdown_content": markdown_content,
            "status_code": response.status_code,
            "content_length": len(markdown_content),
        }
    except Exception as e:
        return {"error": f"Fetch URL error: {e!s}", "url": url}


# ======================
# Morph: Fast Apply Tool
# ======================

MORPH_API_URL = "https://api.morphllm.com/v1/chat/completions"
FAST_APPLY_DEFAULT_MODEL = "auto"


def fast_apply(
    file_path: str,
    instruction: str,
    code_edit: str,
    model: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Apply code edits using Morph Fast Apply (OpenAI-compatible API).

    Args:
        file_path: Target file path to update.
        instruction: Brief first-person description of the change (first person).
        code_edit: Patch-style update with // ... existing code ... placeholders.
        model: Morph model to use (default: "auto").
        timeout: Request timeout in seconds.

    Returns:
        Dict with status and metadata, or error.
    """
    api_key = os.environ.get("MORPH_API_KEY")
    if not api_key:
        return {"error": "MORPH_API_KEY not configured in environment."}

    target_path = Path(file_path).expanduser()
    if not target_path.is_absolute():
        target_path = (Path.cwd() / target_path).resolve()

    original_code = ""
    if target_path.exists():
        try:
            original_code = target_path.read_text()
        except Exception as e:  # noqa: BLE001
            return {"error": f"Failed to read file: {e!s}", "path": str(target_path)}

    payload = {
        "model": model or FAST_APPLY_DEFAULT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"<instruction>{instruction}</instruction>\n"
                    f"<code>{original_code}</code>\n"
                    f"<update>{code_edit}</update>"
                ),
            }
        ],
        "temperature": 0.0,
        "max_tokens": 8192,
    }

    try:
        response = requests.post(
            MORPH_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        merged_code = response.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        return {"error": f"Fast apply error: {e!s}", "path": str(target_path)}

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(merged_code)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Failed to write file: {e!s}", "path": str(target_path)}

    return {
        "status": "ok",
        "path": str(target_path),
        "bytes_written": len(merged_code.encode("utf-8")),
    }


# ======================
# Morph: WarpGrep Tool
# ======================

WARP_GREP_MODEL = "morph-warp-grep-v1"
MAX_TURNS = 4
MAX_GREP_LINES = 200
MAX_LIST_LINES = 200
MAX_READ_LINES = 800

WARP_GREP_SYSTEM_PROMPT = r"""You are a code search agent. Your task is to find all relevant code for a given search_string.

### workflow
You have exactly 4 turns. The 4th turn MUST be a `finish` call. Each turn allows up to 8 parallel tool calls.

- Turn 1: Map the territory OR dive deep (based on search_string specificity)
- Turn 2-3: Refine based on findings
- Turn 4: MUST call `finish` with all relevant code locations
- You MAY call `finish` early if confident—but never before at least 1 search turn.
- The user strongly prefers if you can call the finish tool early, but you must be correct

Remember, if the task feels easy to you, it is strongly desireable to call 'finish' early using fewer turns, but quality over speed

### tools
Tool calls use nested XML elements:
```xml
<tool_name>
  <parameter>value</parameter>
</tool_name>
```

### `list_directory`
Directory tree view. Shows structure of a path, optionally filtered by regex pattern.

Elements:
- `<path>` (required): Directory path to list (use `.` for repo root)
- `<pattern>` (optional): Regex to filter results

Examples:
```
<list_directory>
  <path>src/services</path>
</list_directory>

<list_directory>
  <path>lib/utils</path>
  <pattern>.*\.(ts|js)$</pattern>
</list_directory>
```

### `read`
Read file contents. Supports multiple line ranges.
- Returns numbered lines for easy reference
- ALWAYS include import statements (usually lines 1-20). Better to over-include than miss context.

Elements:
- `<path>` (required): File path to read
- `<lines>` (optional): Line ranges like "1-50,75-80,100-120" (omit to read entire file)

Examples:
```
<read>
  <path>src/main.py</path>
</read>

<read>
  <path>src/auth.py</path>
  <lines>1-20,45-80,150-200</lines>
</read>
```

### `grep`
Search for pattern matches across files. Returns matches with 1 line of context above and below.
- Match lines use `:` separator → `filepath:linenum:content`
- Context lines use `-` separator → `filepath-linenum-content`

Elements:
- `<pattern>` (required): Search pattern (regex). Use `(a|b)` for OR patterns.
- `<sub_dir>` (optional): Subdirectory to search in (defaults to `.`)
- `<glob>` (optional): File pattern filter like `*.py` or `*.{ts,tsx}`

Examples:
```
<grep>
  <pattern>(authenticate|authorize|login)</pattern>
  <sub_dir>src/auth/</sub_dir>
</grep>

<grep>
  <pattern>class.*(Service|Controller)</pattern>
  <glob>*.{ts,js}</glob>
</grep>

<grep>
  <pattern>(DB_HOST|DATABASE_URL|connection)</pattern>
  <glob>*.{py,yaml,env}</glob>
  <sub_dir>lib/</sub_dir>
</grep>
```

### `finish`
Submit final answer with all relevant code locations. Uses nested `<file>` elements.

File elements:
- `<path>` (required): File path
- `<lines>` (optional): Line ranges like "1-50,75-80" (`*` for entire file)

ALWAYS include import statements (usually lines 1-20). Better to over-include than miss context.

Examples:
```
<finish>
  <file>
    <path>src/auth.py</path>
    <lines>1-15,25-50,75-80</lines>
  </file>
  <file>
    <path>src/models/user.py</path>
    <lines>*</lines>
  </file>
</finish>
```
<strategy>
**Before your first tool call, classify the search_string:**

| Search_string Type | Round 1 Strategy | Early Finish? |
|------------|------------------|---------------|
| **Specific** (function name, error string, unique identifier) | 8 parallel greps on likely paths | Often by round 2 |
| **Conceptual** (how does X work, where is Y handled) | list_directory + 2-3 broad greps | Rarely early |
| **Exploratory** (find all tests, list API endpoints) | list_directory at multiple depths | Usually needs 3 rounds |

**Parallel call patterns:**
- **Shotgun grep**: Same pattern, 8 different directories—fast coverage
- **Variant grep**: 8 pattern variations (synonyms, naming conventions)—catches inconsistent codebases
- **Funnel**: 1 list_directory + 7 greps—orient and search simultaneously
- **Deep read**: 8 reads on files you already identified—gather full context fast

**Tool call expectations:**
- Low quality tool calls are ones that give back sparse information. This either means they are not well thought out and are not educated guesses OR, they are too broad and give back too many results.
- High quality tool calls strike a balance between complexity in the tool call to exclude results we know we don't want, and how wide the search space is so that we don't miss anything. It is ok to start off with wider search spaces, but is imperative that you use your intuition from there on out and seek high quality tool calls only.
- You are not starting blind, you have some information about root level repo structure going in, so use that to prevent making trivial repo wide queries.
- The grep tool shows you which file path and line numbers the pattern was found in, use this information smartly when trying to read the file.
</strategy>

<output_format>
EVERY response MUST follow this exact format:

1. First, wrap your reasoning in `<think>...</think>` tags containing:
   - Search_string classification (specific/conceptual/exploratory)
   - Confidence estimate (can I finish in 1-2 rounds?)
   - This round's parallel strategy
   - What signals would let me finish early?

2. Then, output up to 8 tool calls using nested XML elements.

Example:
```
<think>
This is a specific search_string about authentication. I'll grep for auth-related patterns.
High confidence I can finish in 2 rounds if I find the auth module. I have already been shown the repo's structure at root
Strategy: Shotgun grep across likely directories.
</think>
<grep>
  <pattern>(authenticate|login|session)</pattern>
  <sub_dir>src/auth/</sub_dir>
</grep>
<grep>
  <pattern>(middleware|interceptor)</pattern>
  <glob>*.{ts,js}</glob>
</grep>
<list_directory>
  <path>src/auth</path>
</list_directory>
```

Finishing example:
```
<think>
I think I have a rough idea, but this is my last turn so I must call the finish tool regardless.
</think>
<finish>
  <file>
    <path>src/auth/login.py</path>
    <lines>1-50</lines>
  </file>
  <file>
    <path>src/middleware/session.py</path>
    <lines>10-80</lines>
  </file>
</finish>
```

No commentary outside `<think>`. No explanations after tool calls.
</output_format>

<finishing_requirements>
When calling `finish`:
- Include the import section (typically lines 1-20) of each file
- Include all function/class definitions that are relevant
- Include any type definitions, interfaces, or constants used
- Better to over-include than leave the user missing context
- If unsure about boundaries, include more rather than less
</finishing_requirements>
"""


@dataclass
class _ToolCall:
    name: str
    args: dict[str, Any]


def _call_morph(messages: list[dict[str, str]]) -> str:
    api_key = os.environ.get("MORPH_API_KEY")
    if not api_key:
        raise RuntimeError("MORPH_API_KEY not configured in environment.")
    response = requests.post(
        MORPH_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": WARP_GREP_MODEL,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 2048,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_xml_elements(content: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for match in re.finditer(r"<(\\w+)>(.*?)</\\1>", content, re.DOTALL):
        key = match.group(1)
        value = match.group(2).strip()
        if key == "file":
            args.setdefault("files", [])
            args["files"].append(_parse_xml_elements(value))
        else:
            args[key] = value
    return args


def _parse_tool_calls(response: str) -> list[_ToolCall]:
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    tool_calls: list[_ToolCall] = []
    for tool_name in ["grep", "read", "list_directory", "finish"]:
        pattern = rf"<{tool_name}>(.*?)</{tool_name}>"
        for match in re.finditer(pattern, response, re.DOTALL):
            content = match.group(1)
            args = _parse_xml_elements(content)
            tool_calls.append(_ToolCall(name=tool_name, args=args))
    return tool_calls


def _safe_path(repo_root: Path, rel_path: str) -> Path:
    candidate = (repo_root / rel_path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        raise ValueError("Path outside repo root") from None
    return candidate


def _execute_grep(repo_root: Path, pattern: str, sub_dir: str = ".", glob: str | None = None) -> str:
    if shutil.which("rg") is None:
        return "Error: ripgrep (rg) not installed"
    try:
        path = _safe_path(repo_root, sub_dir)
    except ValueError as e:
        return f"Error: {e}"
    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "-C",
        "1",
    ]
    if glob:
        cmd.extend(["--glob", glob])
    cmd.extend([pattern, str(path)])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        return "Error: search timed out"
    except Exception as e:  # noqa: BLE001
        return f"Error: {e!s}"

    lines = output.strip().split("\n") if output.strip() else []
    if len(lines) > MAX_GREP_LINES:
        return (
            "query not specific enough, tool called tried to return too much context and failed"
        )
    return output.strip() if output.strip() else "no matches"


def _execute_read(repo_root: Path, path: str, lines: str | None = None) -> str:
    try:
        file_path = _safe_path(repo_root, path)
    except ValueError as e:
        return f"Error: {e}"
    if not file_path.exists():
        return f"Error: file not found: {path}"
    try:
        all_lines = file_path.read_text().splitlines()
    except Exception as e:  # noqa: BLE001
        return f"Error: {e!s}"

    if lines:
        selected = []
        for range_part in lines.split(","):
            if "-" in range_part:
                start, end = map(int, range_part.split("-"))
            else:
                start = end = int(range_part)
            selected.extend(range(start - 1, min(end, len(all_lines))))
        output_lines = []
        prev_idx = -2
        for idx in sorted(set(selected)):
            if idx < 0 or idx >= len(all_lines):
                continue
            if prev_idx >= 0 and idx > prev_idx + 1:
                output_lines.append("...")
            output_lines.append(f"{idx + 1}|{all_lines[idx]}")
            prev_idx = idx
    else:
        output_lines = [f"{i + 1}|{line}" for i, line in enumerate(all_lines)]

    if len(output_lines) > MAX_READ_LINES:
        output_lines = output_lines[:MAX_READ_LINES]
        output_lines.append(f"... truncated ({len(all_lines)} total lines)")
    return "\n".join(output_lines)


def _execute_list_directory(repo_root: Path, path: str, pattern: str | None = None) -> str:
    try:
        dir_path = _safe_path(repo_root, path)
    except ValueError as e:
        return f"Error: {e}"
    if not dir_path.exists():
        return f"Error: directory not found: {path}"

    if shutil.which("tree"):
        cmd = [
            "tree",
            "-L",
            "3",
            "-i",
            "-F",
            "--noreport",
            "-I",
            "__pycache__|node_modules|.git|*.pyc|.DS_Store|.venv|venv|dist|build",
            str(dir_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(repo_root),
            )
            output = result.stdout
        except Exception as e:  # noqa: BLE001
            return f"Error: {e!s}"
        lines = output.strip().split("\n") if output.strip() else []
    else:
        lines = _fallback_list_dir(dir_path, pattern)

    if pattern and lines:
        try:
            compiled = re.compile(pattern)
            lines = [l for l in lines if compiled.search(l)]
        except re.error:
            pass

    if len(lines) > MAX_LIST_LINES:
        return (
            "query not specific enough, tool called tried to return too much context and failed"
        )
    return "\n".join(lines)


def _fallback_list_dir(dir_path: Path, pattern: str | None = None, max_depth: int = 3) -> list[str]:
    excludes = {"node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".git"}
    compiled = re.compile(pattern) if pattern else None
    lines: list[str] = []

    def walk(path: Path, depth: int = 0) -> None:
        if depth > max_depth:
            return
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith(".") and item.name not in {".env"}:
                    continue
                if item.name in excludes:
                    continue
                suffix = "/" if item.is_dir() else ""
                line = f"{'  ' * depth}{item.name}{suffix}"
                if compiled is None or compiled.search(line):
                    lines.append(line)
                if item.is_dir():
                    walk(item, depth + 1)
        except PermissionError:
            return

    walk(dir_path)
    return lines[:MAX_LIST_LINES]


def _format_result(tool_call: _ToolCall, output: str) -> str:
    if tool_call.name == "grep":
        attrs = f'pattern="{tool_call.args.get("pattern", "")}"'
        if "sub_dir" in tool_call.args:
            attrs += f' sub_dir="{tool_call.args["sub_dir"]}"'
        if "glob" in tool_call.args:
            attrs += f' glob="{tool_call.args["glob"]}"'
        return f"<grep {attrs}>\n{output}\n</grep>"
    if tool_call.name == "read":
        attrs = f'path="{tool_call.args.get("path", "")}"'
        if "lines" in tool_call.args:
            attrs += f' lines="{tool_call.args["lines"]}"'
        return f"<read {attrs}>\n{output}\n</read>"
    if tool_call.name == "list_directory":
        attrs = f'path="{tool_call.args.get("path", "")}"'
        return f"<list_directory {attrs}>\n{output}\n</list_directory>"
    return output


def _format_turn_message(turn: int, chars_used: int = 0, max_chars: int = 160000) -> str:
    remaining = 4 - turn
    if turn >= 3:
        msg = (
            "You have used 3 turns, you only have 1 turn remaining. "
            "You have run out of turns to explore the code base and MUST call the finish tool now"
        )
    else:
        msg = f"You have used {turn} turn{'s' if turn != 1 else ''} and have {remaining} remaining"
    pct = int((chars_used / max_chars) * 100) if max_chars > 0 else 0
    budget = f"<context_budget>{pct}% ({chars_used // 1000}K/{max_chars // 1000}K chars)</context_budget>"
    return f"\n{msg}\n{budget}"


def _resolve_finish(repo_root: Path, finish_call: _ToolCall) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    files = finish_call.args.get("files", [])
    for file_spec in files:
        path = file_spec.get("path", "")
        lines = file_spec.get("lines")
        if lines == "*":
            lines = None
        content = _execute_read(repo_root, path, lines)
        results.append({"path": path, "content": content})
    return results


def _get_repo_structure(repo_root: Path) -> str:
    output = _execute_list_directory(repo_root, ".", None)
    return f"<repo_structure>\n{output}\n</repo_structure>"


def warp_grep(query: str, repo_root: str | None = None) -> dict[str, Any]:
    """Search codebase using Morph WarpGrep (subagent loop).

    Args:
        query: Natural language search request.
        repo_root: Optional repo root (defaults to detected project root or cwd).

    Returns:
        Dict with results list of {path, content} or error.
    """
    api_key = os.environ.get("MORPH_API_KEY")
    if not api_key:
        return {"error": "MORPH_API_KEY not configured in environment."}

    root = Path(repo_root).resolve() if repo_root else None
    if root is None:
        root = settings.project_root or Path.cwd()
    if not root.exists():
        return {"error": f"Repo root does not exist: {root}"}

    messages = [
        {"role": "system", "content": WARP_GREP_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{_get_repo_structure(root)}\n\n<search_string>\n{query}\n</search_string>",
        },
    ]

    chars_used = sum(len(m["content"]) for m in messages)

    for turn in range(MAX_TURNS):
        try:
            response = _call_morph(messages)
        except Exception as e:  # noqa: BLE001
            return {"error": f"WarpGrep API error: {e!s}"}
        messages.append({"role": "assistant", "content": response})
        chars_used += len(response)

        tool_calls = _parse_tool_calls(response)
        if not tool_calls:
            return {"error": "WarpGrep returned no tool calls."}

        finish_call = next((tc for tc in tool_calls if tc.name == "finish"), None)
        if finish_call:
            return {
                "query": query,
                "repo_root": str(root),
                "results": _resolve_finish(root, finish_call),
            }

        results: list[str] = []
        for tc in tool_calls:
            if tc.name == "grep":
                output = _execute_grep(
                    root,
                    tc.args.get("pattern", ""),
                    tc.args.get("sub_dir", "."),
                    tc.args.get("glob"),
                )
            elif tc.name == "read":
                output = _execute_read(root, tc.args.get("path", ""), tc.args.get("lines"))
            elif tc.name == "list_directory":
                output = _execute_list_directory(
                    root, tc.args.get("path", "."), tc.args.get("pattern")
                )
            else:
                output = f"Unknown tool: {tc.name}"
            results.append(_format_result(tc, output))

        result_content = "\n\n".join(results) + _format_turn_message(turn + 1, chars_used)
        messages.append({"role": "user", "content": result_content})
        chars_used += len(result_content)

    return {"error": "WarpGrep did not finish within turn limit."}
