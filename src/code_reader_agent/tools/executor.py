"""Runtime executor for registered tools."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from time import perf_counter
from typing import Any

from code_reader_agent.models import PlannedToolCall, ToolCallRecord
from code_reader_agent.tools.models import ToolDefinition, ToolExecutionContext, ToolResult
from code_reader_agent.tools.registry import ToolRegistry, default_tool_registry
from code_reader_agent.tools.result_processor import ToolResultProcessor
from code_reader_agent.tools.trace import ToolTraceStore


PATH_ARGUMENTS = {"relative_path", "file_path"}
PATH_ARGUMENTS_BY_TOOL = {
    "read_file": {"path"},
    "read_file_chunk": {"path"},
    "get_file_metadata": {"path"},
    "parse_package_scripts": {"path"},
}


class ToolExecutor:
    """Execute registered tools with mode, permission, path, and trace controls."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        processor: ToolResultProcessor | None = None,
        trace_store: ToolTraceStore | None = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.processor = processor or ToolResultProcessor()
        self.trace_store = trace_store or ToolTraceStore()

    def execute(self, call: PlannedToolCall, context: ToolExecutionContext) -> ToolResult:
        """Execute a planned tool call and return a processed result."""

        start = perf_counter()
        tool = self.registry.get_tool(call.tool_name)
        if tool is None:
            return self._error(call, context, start, f"Tool is not registered: {call.tool_name}")

        validation_error = self._validate(tool, call.args, context)
        if validation_error:
            return self._error(call, context, start, validation_error)

        try:
            raw_output = self._run_with_timeout(tool, dict(call.args), context)
            result = self.processor.process(
                tool_name=tool.name,
                raw_output=raw_output,
                args=dict(call.args),
                reason=call.purpose,
            )
        except TimeoutError:
            result = self.processor.error(
                tool_name=tool.name,
                args=dict(call.args),
                reason=call.purpose,
                error=f"Tool timed out after {tool.timeout_ms} ms: {tool.name}",
            )
        except Exception as exc:
            result = self.processor.error(
                tool_name=tool.name,
                args=dict(call.args),
                reason=call.purpose,
                error=str(exc),
            )

        duration_ms = _duration_ms(start)
        return self._attach_trace_and_record(result, call, duration_ms)

    def _validate(self, tool: ToolDefinition, args: dict[str, Any], context: ToolExecutionContext) -> str | None:
        if context.mode not in tool.available_in_modes:
            return f"Tool is not available in mode {context.mode}: {tool.name}"
        if tool.permission not in context.allowed_permissions:
            return f"Tool permission is not allowed in this context: {tool.permission}"
        if context.mode == "ask" and (tool.permission != "read" or tool.risk_level != "safe"):
            return "Ask mode only allows safe read tools."

        schema_error = _validate_input_schema(tool.input_schema, args)
        if schema_error:
            return schema_error

        path_error = _validate_path_arguments(tool.name, args, context.project_path)
        if path_error:
            return path_error
        return None

    def _run_with_timeout(self, tool: ToolDefinition, args: dict[str, Any], context: ToolExecutionContext) -> Any:
        timeout_ms = tool.timeout_ms
        if timeout_ms is None:
            return tool.handler(args, context)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool.handler, args, context)
        try:
            return future.result(timeout=timeout_ms / 1000)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _error(self, call: PlannedToolCall, context: ToolExecutionContext, start: float, message: str) -> ToolResult:
        result = self.processor.error(
            tool_name=call.tool_name,
            args=dict(call.args),
            reason=call.purpose,
            error=message,
        )
        return self._attach_trace_and_record(result, call, _duration_ms(start))

    def _attach_trace_and_record(self, result: ToolResult, call: PlannedToolCall, duration_ms: int) -> ToolResult:
        trace = self.trace_store.record(
            tool_name=result.tool_name,
            input=dict(call.args),
            reason=call.purpose,
            success=result.success,
            output_summary=result.output_summary,
            duration_ms=duration_ms,
        )
        result.trace = trace
        result.tool_call = ToolCallRecord(
            tool_name=result.tool_name,
            input_summary=_input_summary(call.args),
            output_summary=result.output_summary,
            status="success" if result.success else "error",
            error=result.error,
            reason=call.purpose,
            duration_ms=duration_ms,
            timestamp=trace.timestamp,
            input=dict(call.args),
        )
        return result


def _validate_input_schema(schema: dict[str, Any], args: dict[str, Any]) -> str | None:
    required = schema.get("required", [])
    if isinstance(required, list):
        for name in required:
            if name not in args or args.get(name) in (None, ""):
                return f"Missing required tool argument: {name}"

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return None
    for name, config in properties.items():
        if name not in args or not isinstance(config, dict):
            continue
        expected = config.get("type")
        value = args[name]
        if expected == "string" and not isinstance(value, str):
            return f"Tool argument must be a string: {name}"
        if expected == "integer" and not isinstance(value, int):
            return f"Tool argument must be an integer: {name}"
        if expected == "array" and not isinstance(value, list):
            return f"Tool argument must be an array: {name}"
    return None


def _validate_path_arguments(tool_name: str, args: dict[str, Any], project_path: str) -> str | None:
    names = set(PATH_ARGUMENTS)
    names.update(PATH_ARGUMENTS_BY_TOOL.get(tool_name, set()))
    root = Path(project_path).expanduser().resolve()
    for name in names:
        value = args.get(name)
        if not isinstance(value, str) or not value:
            continue
        candidate = (root / value).resolve()
        if not candidate.is_relative_to(root):
            return "Path traversal outside the project root is not allowed."
    return None


def _input_summary(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts = [f"{key}={value}" for key, value in sorted(args.items())]
    summary = ", ".join(parts)
    return summary[:240]


def _duration_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
