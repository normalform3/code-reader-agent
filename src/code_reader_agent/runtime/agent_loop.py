"""Minimal read-only LLM agent loop for CodeReader Agent."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError

from code_reader_agent.interpreter import interpret_project
from code_reader_agent.models import (
    AgentRunResult,
    AgentStep,
    EvidenceRef,
    ToolCallRecord,
)
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import ProjectScanError, scan_project
from code_reader_agent.tools.read_only import ReadOnlyToolError, read_file, search_code
from code_reader_agent.runtime.llm_client import LLMConfigurationError, LiteLLMClient


MAX_TOOL_OUTPUT_CHARS = 10_000
AGENT_SYSTEM_PROMPT = """You are CodeReader Agent, a read-only codebase onboarding agent.

You may inspect the local project only through the provided tools.
Do not claim you read a file unless a tool result contains that file content.
Do not ask to edit files, run shell commands, use git, or read secrets.

When you have enough evidence, respond with a JSON object only:
{
  "answer": "...",
  "skill": "project_overview_skill | setup_analysis_skill | frontend_analysis_skill | api_flow_skill | auth_flow_skill",
  "evidence": [{"path": "...", "reason": "...", "source": "...", "start_line": 1, "end_line": 3, "excerpt": "..."}],
  "read_files": ["..."],
  "warnings": ["..."],
  "suggested_questions": ["..."]
}
"""


class AgentLLMClient(Protocol):
    """Protocol used by tests and the production LiteLLM adapter."""

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Return an OpenAI-compatible chat completion object or dictionary."""


def run_agent_loop(
    project_path: str,
    question: str,
    max_steps: int = 6,
    llm_client: AgentLLMClient | None = None,
) -> AgentRunResult:
    """Run a bounded read-only LLM tool-calling loop with deterministic fallback."""

    fallback = interpret_project(project_path, question)
    client = llm_client or LiteLLMClient()
    if llm_client is None and isinstance(client, LiteLLMClient) and not client.is_configured():
        return _fallback_result(
            fallback,
            warning="Missing DASHSCOPE_API_KEY or DASHSCOPE_BASE_URL; deterministic fallback was used.",
        )

    messages = _initial_messages(project_path, question)
    tool_calls: list[ToolCallRecord] = []
    agent_steps: list[AgentStep] = []
    evidence: list[EvidenceRef] = []
    read_files: list[str] = []
    warnings: list[str] = []

    for step_index in range(1, max(1, max_steps) + 1):
        try:
            response = client.complete(messages, AGENT_TOOL_DEFINITIONS)
        except (LLMConfigurationError, Exception) as exc:
            return _fallback_result(fallback, warning=f"LLM agent loop failed: {exc}")

        message = _extract_message(response)
        content = _message_content(message)
        tool_call_items = _message_tool_calls(message)
        agent_steps.append(
            AgentStep(
                index=len(agent_steps) + 1,
                kind="llm",
                title="LLM decision",
                summary=_summarize_llm_message(content, tool_call_items),
            )
        )

        if tool_call_items:
            messages.append(_assistant_message_for_history(message))
            for tool_call in tool_call_items:
                tool_name = _tool_call_name(tool_call)
                arguments = _tool_call_arguments(tool_call)
                result = _execute_tool(project_path, tool_name, arguments)
                tool_calls.append(result.tool_call)
                evidence.extend(result.evidence)
                read_files.extend(result.read_files)
                warnings.extend(result.warnings)
                agent_steps.append(
                    AgentStep(
                        index=len(agent_steps) + 1,
                        kind="tool",
                        title=tool_name,
                        summary=result.tool_call.output_summary,
                        tool_name=tool_name,
                        status=result.tool_call.status,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _tool_call_id(tool_call),
                        "content": _truncate_tool_output(result.content),
                    }
                )
            continue

        parsed = _parse_final_json(content)
        if parsed is None:
            return _fallback_result(fallback, warning="LLM final answer was not valid JSON; deterministic fallback was used.")

        parsed_evidence = _parse_evidence(parsed.get("evidence", []))
        final_evidence = _dedupe_evidence([*evidence, *parsed_evidence])
        final_read_files = _dedupe_strings([*read_files, *_string_list(parsed.get("read_files"))])
        final_warnings = _dedupe_strings([*warnings, *_string_list(parsed.get("warnings"))])
        final_questions = _string_list(parsed.get("suggested_questions")) or fallback.suggested_questions
        agent_steps.append(
            AgentStep(
                index=len(agent_steps) + 1,
                kind="final",
                title="Final answer",
                summary=str(parsed.get("answer") or "").strip()[:300],
            )
        )
        return AgentRunResult(
            project_name=fallback.project_name,
            question=question,
            skill=str(parsed.get("skill") or fallback.skill),
            final_answer=str(parsed.get("answer") or fallback.overview),
            evidence=final_evidence or fallback.evidence,
            tool_calls=tool_calls,
            read_files=final_read_files,
            suggested_questions=final_questions,
            warnings=final_warnings,
            agent_steps=agent_steps,
            used_llm=True,
            fallback_used=False,
            fallback_result=None,
        )

    return _fallback_result(fallback, warning=f"LLM agent loop exceeded max_steps={max_steps}; deterministic fallback was used.")


class _ToolResult:
    def __init__(
        self,
        content: str,
        tool_call: ToolCallRecord,
        evidence: list[EvidenceRef] | None = None,
        read_files: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.content = content
        self.tool_call = tool_call
        self.evidence = evidence or []
        self.read_files = read_files or []
        self.warnings = warnings or []


def _initial_messages(project_path: str, question: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n".join(
                [
                    f"project_path: {project_path}",
                    f"user_question: {question}",
                    "Use tools to inspect the project before answering.",
                ]
            ),
        },
    ]


def _execute_tool(project_path: str, tool_name: str, arguments: dict[str, Any]) -> _ToolResult:
    if tool_name == "scan_project":
        return _run_scan_project(project_path)
    if tool_name == "build_repo_map":
        return _run_build_repo_map(project_path)
    if tool_name == "read_file":
        relative_path = str(arguments.get("relative_path") or arguments.get("path") or "")
        line_range = _line_range(arguments)
        return _run_read_file(project_path, relative_path, line_range)
    if tool_name == "search_code":
        query = str(arguments.get("query") or "")
        globs = arguments.get("globs")
        return _run_search_code(project_path, query, globs if isinstance(globs, list) else None)

    return _ToolResult(
        content=json.dumps({"error": f"Tool is not allowed: {tool_name}"}, ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name=tool_name,
            input_summary="blocked",
            output_summary=f"Tool is not allowed: {tool_name}",
            status="error",
            error=f"Tool is not allowed: {tool_name}",
        ),
        warnings=[f"LLM requested disallowed tool: {tool_name}."],
    )


def _run_scan_project(project_path: str) -> _ToolResult:
    try:
        result = scan_project(project_path)
    except ProjectScanError as exc:
        return _error_tool_result("scan_project", project_path, str(exc))
    payload = result.model_dump()
    return _ToolResult(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name="scan_project",
            input_summary=project_path,
            output_summary=f"Scanned {len(result.file_tree)} file tree entries.",
            status="success",
        ),
        warnings=result.warnings,
    )


def _run_build_repo_map(project_path: str) -> _ToolResult:
    try:
        repo_map = build_repo_map(scan_project(project_path))
    except ProjectScanError as exc:
        return _error_tool_result("build_repo_map", project_path, str(exc))
    return _ToolResult(
        content=json.dumps(repo_map.model_dump(), ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name="build_repo_map",
            input_summary=project_path,
            output_summary=f"Built Repo Map with {len(repo_map.modules)} modules.",
            status="success",
        ),
        evidence=[
            EvidenceRef(
                path=item.path,
                reason=item.reason,
                source=item.collected_by_tool,
                start_line=item.start_line,
                end_line=item.end_line,
                excerpt=item.excerpt,
            )
            for item in repo_map.evidence
        ],
        warnings=repo_map.warnings,
    )


def _run_read_file(project_path: str, relative_path: str, line_range: tuple[int, int] | None) -> _ToolResult:
    try:
        result = read_file(project_path, relative_path, line_range=line_range)
    except (ReadOnlyToolError, ValueError) as exc:
        return _error_tool_result("read_file", relative_path, str(exc), warning=str(exc))
    evidence = EvidenceRef(
        path=result.path,
        reason="LLM requested file content.",
        source="read_file",
        start_line=result.start_line,
        end_line=result.end_line,
        excerpt=result.content,
    )
    return _ToolResult(
        content=json.dumps(result.model_dump(), ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name="read_file",
            input_summary=result.path,
            output_summary=f"Read lines {result.start_line}-{result.end_line}.",
            status="success",
        ),
        evidence=[evidence],
        read_files=[result.path],
        warnings=result.warnings,
    )


def _run_search_code(project_path: str, query: str, globs: list[Any] | None) -> _ToolResult:
    try:
        result = search_code(project_path, query, globs=[str(item) for item in globs] if globs else None)
    except (ReadOnlyToolError, ValueError, ProjectScanError) as exc:
        return _error_tool_result("search_code", query, str(exc), warning=str(exc))
    return _ToolResult(
        content=json.dumps(result.model_dump(), ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name="search_code",
            input_summary=query,
            output_summary=f"{result.used_backend} returned {len(result.matches)} matches.",
            status="success",
        ),
        evidence=[
            EvidenceRef(
                path=match.path,
                reason=f"Search match for {query}.",
                source="search_code",
                start_line=match.line_number,
                end_line=match.line_number,
                excerpt=match.line,
            )
            for match in result.matches
        ],
        warnings=result.warnings,
    )


def _error_tool_result(tool_name: str, input_summary: str, error: str, warning: str | None = None) -> _ToolResult:
    return _ToolResult(
        content=json.dumps({"error": error}, ensure_ascii=False),
        tool_call=ToolCallRecord(
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=error,
            status="error",
            error=error,
        ),
        warnings=[warning] if warning else [],
    )


def _fallback_result(fallback: Any, warning: str) -> AgentRunResult:
    warnings = _dedupe_strings([*fallback.warnings, warning])
    return AgentRunResult(
        project_name=fallback.project_name,
        question=fallback.question,
        skill=fallback.skill,
        final_answer=f"{fallback.overview}\n\n{fallback.setup_summary}",
        evidence=fallback.evidence,
        tool_calls=fallback.tool_calls,
        read_files=fallback.read_files,
        suggested_questions=fallback.suggested_questions,
        warnings=warnings,
        agent_steps=[
            AgentStep(
                index=1,
                kind="fallback",
                title="Deterministic fallback",
                summary=warning,
                status="success",
            )
        ],
        used_llm=False,
        fallback_used=True,
        fallback_result=fallback,
    )


def _extract_message(response: Any) -> Any:
    if isinstance(response, dict):
        return response["choices"][0]["message"]
    return response.choices[0].message


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def _message_tool_calls(message: Any) -> list[Any]:
    if isinstance(message, dict):
        return list(message.get("tool_calls") or [])
    return list(getattr(message, "tool_calls", None) or [])


def _assistant_message_for_history(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    payload: dict[str, Any] = {"role": "assistant", "content": getattr(message, "content", None)}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": _tool_call_id(item),
                "type": "function",
                "function": {
                    "name": _tool_call_name(item),
                    "arguments": json.dumps(_tool_call_arguments(item), ensure_ascii=False),
                },
            }
            for item in tool_calls
        ]
    return payload


def _tool_call_id(tool_call: Any) -> str:
    if isinstance(tool_call, dict):
        return str(tool_call.get("id") or "tool_call")
    return str(getattr(tool_call, "id", "tool_call"))


def _tool_call_name(tool_call: Any) -> str:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return str(getattr(function, "name", "") or "")


def _tool_call_arguments(tool_call: Any) -> dict[str, Any]:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    raw_arguments = function.get("arguments") if isinstance(function, dict) else getattr(function, "arguments", "{}")
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _line_range(arguments: dict[str, Any]) -> tuple[int, int] | None:
    start_line = arguments.get("start_line")
    end_line = arguments.get("end_line")
    if isinstance(start_line, int) and isinstance(end_line, int):
        return start_line, end_line
    return None


def _parse_final_json(content: str) -> dict[str, Any] | None:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_evidence(raw_evidence: Any) -> list[EvidenceRef]:
    if not isinstance(raw_evidence, list):
        return []
    parsed: list[EvidenceRef] = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append(EvidenceRef.model_validate(item))
        except ValidationError:
            continue
    return parsed


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _dedupe_evidence(evidence: list[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[tuple[str, str, str, int | None]] = set()
    unique: list[EvidenceRef] = []
    for item in evidence:
        key = (item.path, item.reason, item.source, item.start_line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _truncate_tool_output(content: str) -> str:
    if len(content) <= MAX_TOOL_OUTPUT_CHARS:
        return content
    return content[:MAX_TOOL_OUTPUT_CHARS] + "\n...TRUNCATED..."


def _summarize_llm_message(content: str, tool_calls: list[Any]) -> str:
    if tool_calls:
        names = ", ".join(_tool_call_name(item) for item in tool_calls)
        return f"Requested tools: {names}"
    return content[:300] if content else "No tool call returned."


AGENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "scan_project",
            "description": "Scan the project file tree and detect stack metadata.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_repo_map",
            "description": "Build a deterministic Repo Map with modules, files, and evidence.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a non-sensitive project file by relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["relative_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search project code for a literal query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "globs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]
