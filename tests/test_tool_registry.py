from __future__ import annotations

from typing import Any

from code_reader_agent.tools.models import ToolDefinition, ToolExecutionContext
from code_reader_agent.tools.registry import ToolRegistry, default_tool_registry


def _handler(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, str]:
    return {"ok": "yes"}


def _definition(name: str = "demo_tool", category: str = "diagnostic") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="Demo tool.",
        category=category,  # type: ignore[arg-type]
        permission="read",
        available_in_modes=["ask"],
        input_schema={"type": "object", "required": [], "properties": {}},
        handler=_handler,
        risk_level="safe",
    )


def test_tool_registry_registers_and_replaces_tools() -> None:
    registry = ToolRegistry()
    first = _definition("demo_tool")
    replacement = ToolDefinition(
        name="demo_tool",
        description="Replacement.",
        category="search",
        permission="read",
        available_in_modes=["ask"],
        input_schema={},
        handler=_handler,
        risk_level="safe",
    )

    registry.register(first)
    registry.register(replacement)

    assert registry.get_tool("demo_tool") is replacement
    assert registry.get_tool("missing") is None
    assert registry.list_tools() == [replacement]


def test_tool_registry_lists_by_mode_and_category() -> None:
    registry = ToolRegistry([_definition("search_demo", "search"), _definition("parser_demo", "parser")])

    assert {tool.name for tool in registry.list_tools_by_mode("ask")} == {"search_demo", "parser_demo"}
    assert [tool.name for tool in registry.list_tools_by_category("search")] == ["search_demo"]


def test_default_tool_registry_contains_mvp_ask_tools() -> None:
    registry = default_tool_registry()
    names = {tool.name for tool in registry.list_tools_by_mode("ask")}

    assert {
        "list_files",
        "read_file",
        "read_file_chunk",
        "search_keyword",
        "search_file_by_name",
        "query_code_index",
        "parse_controller",
        "parse_api_calls",
    } <= names
    assert all(tool.permission == "read" and tool.risk_level == "safe" for tool in registry.list_tools_by_mode("ask"))
