"""Request-local trace store for runtime tool calls."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from code_reader_agent.tools.models import ToolTrace


class ToolTraceStore:
    """Collect observable traces for one Ask request."""

    def __init__(self) -> None:
        self._traces: list[ToolTrace] = []

    def record(
        self,
        *,
        tool_name: str,
        input: dict[str, object],
        reason: str,
        success: bool,
        output_summary: str,
        duration_ms: int,
    ) -> ToolTrace:
        """Append and return one trace record."""

        trace = ToolTrace(
            id=f"tool-{uuid4().hex[:12]}",
            tool_name=tool_name,
            input=dict(input),
            reason=reason,
            success=success,
            output_summary=output_summary,
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._traces.append(trace)
        return trace

    def list_traces(self) -> list[ToolTrace]:
        """Return recorded traces."""

        return list(self._traces)
