"""Linear extension for deepagents-cli."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from deepagents_cli.linear_ids import is_linear_identifier

LINEAR_API_URL = os.environ.get("LINEAR_API_URL", "https://api.linear.app/graphql")
LINEAR_TIMEOUT = 30


class LinearAPIError(RuntimeError):
    """Raised when the Linear API request fails."""


@dataclass(frozen=True)
class LinearIssue:
    id: str
    identifier: str
    title: str
    description: str
    state: str | None
    team: str | None
    assignee: str | None
    created_at: str | None
    updated_at: str | None


def _read_auth_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _get_api_key() -> str | None:
    env_key = os.environ.get("LINEAR_API_KEY")
    if env_key:
        return env_key

    candidates = [
        Path.home() / ".deepagents" / "auth.json",
    ]
    for path in candidates:
        data = _read_auth_file(path)
        if not data:
            continue
        linear = data.get("linear") if isinstance(data, dict) else None
        if isinstance(linear, dict):
            api_key = linear.get("apiKey") or linear.get("api_key")
            if api_key:
                return api_key
        api_key = data.get("linearApiKey") if isinstance(data, dict) else None
        if api_key:
            return api_key
    return None


def _require_api_key() -> str:
    api_key = _get_api_key()
    if not api_key:
        raise LinearAPIError(
            "Linear API key not found. Set LINEAR_API_KEY or add ~/.deepagents/auth.json"
        )
    return api_key


def _graphql_request(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    api_key = _require_api_key()
    response = requests.post(
        LINEAR_API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
        json={"query": query, "variables": variables},
        timeout=LINEAR_TIMEOUT,
    )
    if not response.ok:
        body = response.text[:200]
        raise LinearAPIError(
            f"Linear API error: {response.status_code} {response.reason}"
            + (f" — {body}" if body else "")
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise LinearAPIError(f"Linear API returned invalid JSON: {exc}") from exc
    if payload.get("errors"):
        message = payload["errors"][0].get("message", "Unknown GraphQL error")
        raise LinearAPIError(f"GraphQL error: {message}")
    return payload.get("data", {})


def _parse_identifier(identifier: str) -> tuple[str, int]:
    if "-" not in identifier:
        raise LinearAPIError(f"Invalid issue identifier: {identifier}")
    team_key, number_str = identifier.rsplit("-", 1)
    if not team_key or not number_str.isdigit():
        raise LinearAPIError(f"Invalid issue identifier: {identifier}")
    return team_key.upper(), int(number_str)


def _issue_fields() -> str:
    return """
        id
        identifier
        title
        description
        state { id name type }
        team { id key name }
        assignee { id name }
        createdAt
        updatedAt
    """


def _query_issue_by_identifier(identifier: str) -> dict[str, Any] | None:
    team_key, number = _parse_identifier(identifier)
    query = f"""query($teamKey: String!, $number: Float!) {{
        issues(filter: {{ team: {{ key: {{ eq: $teamKey }} }}, number: {{ eq: $number }} }}) {{
            nodes {{ {_issue_fields()} }}
        }}
    }}"""
    data = _graphql_request(query, {"teamKey": team_key, "number": float(number)})
    issues = data.get("issues", {}).get("nodes", [])
    return issues[0] if issues else None


def _query_issue_by_id(issue_id: str) -> dict[str, Any] | None:
    query_direct = f"""query($id: ID!) {{
        issue(id: $id) {{ {_issue_fields()} }}
    }}"""
    try:
        data = _graphql_request(query_direct, {"id": issue_id})
        issue = data.get("issue")
        if issue:
            return issue
    except LinearAPIError:
        pass

    query_filter = f"""query($id: ID!) {{
        issues(filter: {{ id: {{ eq: $id }} }}) {{
            nodes {{ {_issue_fields()} }}
        }}
    }}"""
    data = _graphql_request(query_filter, {"id": issue_id})
    issues = data.get("issues", {}).get("nodes", [])
    return issues[0] if issues else None


def _resolve_issue(issue_id_or_identifier: str) -> dict[str, Any]:
    issue = None
    if is_linear_identifier(issue_id_or_identifier):
        issue = _query_issue_by_identifier(issue_id_or_identifier)
    if issue is None:
        issue = _query_issue_by_id(issue_id_or_identifier)
    if issue is None:
        raise LinearAPIError(f"Issue not found: {issue_id_or_identifier}")
    return issue


def _resolve_issue_id(issue_id_or_identifier: str) -> str:
    issue = _resolve_issue(issue_id_or_identifier)
    issue_id = issue.get("id")
    if not issue_id:
        raise LinearAPIError(f"Unable to resolve issue id for {issue_id_or_identifier}")
    return issue_id


def _truncate_comment(body: str, max_chars: int = 12000) -> str:
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 100] + "\n\n... (truncated)"


def _list_comments_by_identifier(identifier: str, limit: int) -> list[dict[str, Any]]:
    team_key, number = _parse_identifier(identifier)
    query = """query($teamKey: String!, $number: Float!, $limit: Float!) {
        issues(filter: { team: { key: { eq: $teamKey } }, number: { eq: $number } }) {
            nodes {
                comments(first: $limit) {
                    nodes { body createdAt user { name } }
                }
            }
        }
    }"""
    data = _graphql_request(
        query, {"teamKey": team_key, "number": float(number), "limit": float(limit)}
    )
    comments = (
        data.get("issues", {})
        .get("nodes", [{}])[0]
        .get("comments", {})
        .get("nodes", [])
    )
    return [
        {
            "body": comment.get("body") or "",
            "author": (comment.get("user") or {}).get("name"),
            "createdAt": comment.get("createdAt"),
        }
        for comment in comments
    ]


def _list_comments_by_id(issue_id: str, limit: int) -> list[dict[str, Any]]:
    query_direct = """query($id: ID!, $limit: Float!) {
        issue(id: $id) {
            comments(first: $limit) { nodes { body createdAt user { name } } }
        }
    }"""
    try:
        data = _graphql_request(query_direct, {"id": issue_id, "limit": float(limit)})
        comments = (data.get("issue") or {}).get("comments", {}).get("nodes", [])
    except LinearAPIError:
        query_filter = """query($id: ID!, $limit: Float!) {
            issues(filter: { id: { eq: $id } }) {
                nodes {
                    comments(first: $limit) { nodes { body createdAt user { name } } }
                }
            }
        }"""
        data = _graphql_request(query_filter, {"id": issue_id, "limit": float(limit)})
        comments = (
            data.get("issues", {})
            .get("nodes", [{}])[0]
            .get("comments", {})
            .get("nodes", [])
        )

    return [
        {
            "body": comment.get("body") or "",
            "author": (comment.get("user") or {}).get("name"),
            "createdAt": comment.get("createdAt"),
        }
        for comment in comments
    ]


def _list_workflow_states() -> list[dict[str, Any]]:
    query = """query { workflowStates { nodes { id name type } } }"""
    data = _graphql_request(query, {})
    return data.get("workflowStates", {}).get("nodes", [])


def _resolve_state_id(state_value: str) -> str:
    if "-" in state_value and len(state_value) >= 30:
        return state_value
    states = _list_workflow_states()
    for state in states:
        name = state.get("name")
        if name and name.lower() == state_value.lower():
            return state.get("id")
    raise LinearAPIError(f"Unknown workflow state: {state_value}")


def _normalize_issue(issue: dict[str, Any]) -> LinearIssue:
    state = issue.get("state") or {}
    team = issue.get("team") or {}
    assignee = issue.get("assignee") or {}
    return LinearIssue(
        id=issue.get("id") or "",
        identifier=issue.get("identifier") or "",
        title=issue.get("title") or "",
        description=issue.get("description") or "",
        state=state.get("name"),
        team=team.get("name"),
        assignee=assignee.get("name"),
        created_at=issue.get("createdAt"),
        updated_at=issue.get("updatedAt"),
    )


def linear_get_issue(issue_id_or_identifier: str) -> dict[str, Any]:
    """Get a Linear issue by identifier (TEAM-123) or UUID."""
    issue = _resolve_issue(issue_id_or_identifier)
    normalized = _normalize_issue(issue)
    return {
        "id": normalized.id,
        "identifier": normalized.identifier,
        "title": normalized.title,
        "description": normalized.description,
        "state": normalized.state,
        "team": normalized.team,
        "assignee": normalized.assignee,
        "createdAt": normalized.created_at,
        "updatedAt": normalized.updated_at,
    }


def linear_list_comments(issue_id_or_identifier: str, limit: int = 50) -> list[dict[str, Any]]:
    """List comments for a Linear issue."""
    limit = max(1, min(int(limit), 100))
    if is_linear_identifier(issue_id_or_identifier):
        return _list_comments_by_identifier(issue_id_or_identifier, limit)
    return _list_comments_by_id(issue_id_or_identifier, limit)


def linear_add_comment(issue_id_or_identifier: str, body: str) -> dict[str, Any]:
    """Add a comment to a Linear issue."""
    issue_id = _resolve_issue_id(issue_id_or_identifier)
    body = _truncate_comment(body)
    mutation = """mutation($issueId: ID!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) { success }
    }"""
    data = _graphql_request(mutation, {"issueId": issue_id, "body": body})
    success = (data.get("commentCreate") or {}).get("success") is True
    return {"success": success, "issueId": issue_id}


def linear_comment(issue_id_or_identifier: str, body: str) -> dict[str, Any]:
    """Alias for linear_add_comment."""
    return linear_add_comment(issue_id_or_identifier, body)


def linear_update_issue(
    issue_id_or_identifier: str,
    *,
    title: str | None = None,
    description: str | None = None,
    state: str | None = None,
    priority: int | None = None,
    assignee_id: str | None = None,
) -> dict[str, Any]:
    """Update a Linear issue. Supports title, description, state, priority, assignee_id."""
    issue_id = _resolve_issue_id(issue_id_or_identifier)
    input_payload: dict[str, Any] = {}
    if title is not None:
        input_payload["title"] = title
    if description is not None:
        input_payload["description"] = description
    if priority is not None:
        input_payload["priority"] = int(priority)
    if assignee_id is not None:
        input_payload["assigneeId"] = assignee_id
    if state is not None:
        input_payload["stateId"] = _resolve_state_id(state)
    if not input_payload:
        raise LinearAPIError("No fields provided to update.")

    mutation = """mutation($issueId: ID!, $input: IssueUpdateInput!) {
        issueUpdate(id: $issueId, input: $input) { success issue { id } }
    }"""
    data = _graphql_request(mutation, {"issueId": issue_id, "input": input_payload})
    result = data.get("issueUpdate") or {}
    return {"success": result.get("success") is True, "issueId": issue_id}


def linear_list_statuses() -> list[dict[str, Any]]:
    """List workflow states in Linear."""
    states = _list_workflow_states()
    return [
        {"id": state.get("id"), "name": state.get("name"), "type": state.get("type")}
        for state in states
    ]


def linear_assemble(
    issue_id_or_identifier: str,
    *,
    include_comments: bool = True,
    max_comments: int = 20,
    post_started_comment: bool = False,
) -> dict[str, Any]:
    """Fetch issue context and return an assembly prompt for a multi-step workflow."""
    issue = linear_get_issue(issue_id_or_identifier)
    comments: list[dict[str, Any]] = []
    if include_comments:
        comments = linear_list_comments(issue_id_or_identifier, limit=max_comments)

    if post_started_comment:
        identifier = issue.get("identifier") or issue_id_or_identifier
        title = issue.get("title") or ""
        team = issue.get("team") or ""
        state = issue.get("state") or ""
        assignee = issue.get("assignee") or ""
        lines = [
            "### Assembly Started",
            "",
            f"**Ticket:** {identifier}: {title}",
        ]
        if team:
            lines.append(f"**Team:** {team}")
        if state:
            lines.append(f"**State:** {state}")
        if assignee:
            lines.append(f"**Assignee:** {assignee}")
        lines.extend(
            [
                "_Running scout -> planner -> worker -> reviewer pipeline..._",
                "",
                "---",
                "_assembled via deepagents_",
            ]
        )
        linear_add_comment(issue_id_or_identifier, "\n".join(lines))

    identifier = issue.get("identifier") or issue_id_or_identifier
    prompt = (
        "Assembly context for a Linear issue.\n\n"
        "Suggested workflow:\n"
        "1. Use the task tool with subagents (scout, planner, worker, reviewer).\n"
        "2. Run scout -> planner to produce a concrete plan.\n"
        "3. Run worker -> reviewer loop up to 3 iterations to implement and review.\n"
        "4. Summarize results and remaining issues.\n"
        f"Post progress via `linear_comment` for ticket `{identifier}` after each phase.\n"
        "If a named subagent is unavailable, fall back to `general-purpose`."
    )

    return {
        "issue": issue,
        "comments": comments,
        "assembly_prompt": prompt,
    }


def register(api: Any) -> None:
    """Register Linear tools with the extension API."""
    api.register_tool(linear_get_issue)
    api.register_tool(linear_list_comments)
    api.register_tool(linear_add_comment)
    api.register_tool(linear_comment)
    api.register_tool(linear_update_issue)
    api.register_tool(linear_list_statuses)
    api.register_tool(linear_assemble)
    api.register_prompt(
        "Linear tools available: linear_get_issue, linear_list_comments, "
        "linear_add_comment, linear_comment, linear_update_issue, "
        "linear_list_statuses, linear_assemble."
    )
