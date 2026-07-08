from __future__ import annotations

from pathlib import Path
from typing import Any

from code_reader_agent.models import PlannedToolCall
from code_reader_agent.tools.executor import ToolExecutor
from code_reader_agent.tools.models import ToolDefinition, ToolExecutionContext
from code_reader_agent.tools.registry import ToolRegistry


def test_tool_executor_allows_safe_read_tool_in_ask_mode(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello')\n", encoding="utf-8")
    executor = ToolExecutor()
    context = ToolExecutionContext(project_path=str(tmp_path), mode="ask", allowed_permissions=["read"])

    result = executor.execute(
        PlannedToolCall(
            tool_name="read_file",
            args={"relative_path": "src/main.ts"},
            purpose="Need source evidence.",
        ),
        context,
    )

    assert result.success is True
    assert result.evidence
    assert result.tool_call
    assert result.tool_call.reason == "Need source evidence."
    assert result.tool_call.duration_ms is not None
    assert result.tool_call.timestamp
    assert result.tool_call.input == {"relative_path": "src/main.ts"}


def test_tool_executor_rejects_non_read_or_risky_tools_in_ask_mode(tmp_path: Path) -> None:
    def handler(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, bool]:
        return {"mutated": True}

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="write_file",
                description="Not allowed.",
                category="filesystem",
                permission="write",
                available_in_modes=["ask"],
                input_schema={},
                handler=handler,
                risk_level="dangerous",
            )
        ]
    )
    executor = ToolExecutor(registry=registry)
    context = ToolExecutionContext(project_path=str(tmp_path), mode="ask", allowed_permissions=["read"])

    result = executor.execute(PlannedToolCall(tool_name="write_file", args={}, purpose="Should be blocked."), context)

    assert result.success is False
    assert result.tool_call
    assert result.tool_call.status == "error"
    assert "permission" in result.error or "safe read" in result.error


def test_tool_executor_rejects_path_traversal_before_handler(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope\n", encoding="utf-8")
    executor = ToolExecutor()
    context = ToolExecutionContext(project_path=str(tmp_path), mode="ask", allowed_permissions=["read"])

    result = executor.execute(
        PlannedToolCall(tool_name="read_file", args={"relative_path": "../outside.txt"}, purpose="Bad path."),
        context,
    )

    assert result.success is False
    assert result.tool_call
    assert result.tool_call.status == "error"
    assert "Path traversal" in result.error


def test_tool_executor_records_unknown_tool_and_handler_errors(tmp_path: Path) -> None:
    context = ToolExecutionContext(project_path=str(tmp_path), mode="ask", allowed_permissions=["read"])
    unknown = ToolExecutor().execute(PlannedToolCall(tool_name="missing", args={}, purpose="No such tool."), context)

    assert unknown.success is False
    assert unknown.tool_call
    assert unknown.tool_call.timestamp
    assert "not registered" in unknown.error

    def exploding_handler(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, bool]:
        raise ValueError("boom")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="explode",
                description="Raises.",
                category="diagnostic",
                permission="read",
                available_in_modes=["ask"],
                input_schema={},
                handler=exploding_handler,
                risk_level="safe",
            )
        ]
    )
    failed = ToolExecutor(registry=registry).execute(PlannedToolCall(tool_name="explode", args={}, purpose="Handle errors."), context)

    assert failed.success is False
    assert failed.tool_call
    assert failed.tool_call.output_summary == "boom"
    assert failed.warnings == ["boom"]
