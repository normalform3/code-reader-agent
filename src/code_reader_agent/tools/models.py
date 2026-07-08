"""Runtime tool contracts for evidence collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from code_reader_agent.models import CodeEvidence, EvidenceRef, ProjectMemory, ToolCallRecord


ToolMode = Literal["ask", "plan", "agent"]
ToolPermission = Literal["read", "write", "execute", "network"]
ToolCategory = Literal["filesystem", "search", "parser", "index", "command", "diagnostic"]
ToolCostLevel = Literal["low", "medium", "high"]
ToolRiskLevel = Literal["safe", "caution", "dangerous"]


@dataclass(frozen=True)
class ToolExecutionContext:
    """Request-scoped execution context for a tool call."""

    project_path: str
    mode: ToolMode
    allowed_permissions: list[ToolPermission]
    project_memory: ProjectMemory | None = None


ToolHandler = Callable[[dict[str, Any], ToolExecutionContext], Any]


@dataclass(frozen=True)
class ToolDefinition:
    """Registered runtime tool definition."""

    name: str
    description: str
    category: ToolCategory
    permission: ToolPermission
    available_in_modes: list[ToolMode]
    input_schema: dict[str, Any]
    handler: ToolHandler
    output_schema: dict[str, Any] | None = None
    cost_level: ToolCostLevel = "low"
    risk_level: ToolRiskLevel = "safe"
    timeout_ms: int | None = None


@dataclass
class ToolTrace:
    """Observable record for one runtime tool call."""

    id: str
    tool_name: str
    input: dict[str, Any]
    reason: str
    success: bool
    output_summary: str
    duration_ms: int
    timestamp: str


@dataclass
class ToolResult:
    """Processed result returned by ToolExecutor."""

    tool_name: str
    success: bool
    raw_output: Any = None
    output_summary: str = ""
    evidence: list[CodeEvidence] = field(default_factory=list)
    references: list[EvidenceRef] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    implementation_path: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    trace: ToolTrace | None = None
    tool_call: ToolCallRecord | None = None
