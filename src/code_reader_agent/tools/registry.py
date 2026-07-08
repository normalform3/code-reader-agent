"""Runtime Tool Registry for registered evidence tools."""

from __future__ import annotations

from code_reader_agent.tools.models import ToolCategory, ToolDefinition, ToolMode


class ToolRegistry:
    """Register and list runtime tool definitions."""

    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        """Register or replace a tool definition by name."""

        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Return a registered tool by name."""

        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tools sorted by name."""

        return [self._tools[name] for name in sorted(self._tools)]

    def list_tools_by_mode(self, mode: ToolMode) -> list[ToolDefinition]:
        """Return tools available in the given mode."""

        return [tool for tool in self.list_tools() if mode in tool.available_in_modes]

    def list_tools_by_category(self, category: str) -> list[ToolDefinition]:
        """Return tools in the given category."""

        return [tool for tool in self.list_tools() if tool.category == category]


def default_tool_registry() -> ToolRegistry:
    """Return the built-in runtime Tool Registry."""

    from code_reader_agent.tools.builtin import built_in_tools

    return ToolRegistry(built_in_tools())
