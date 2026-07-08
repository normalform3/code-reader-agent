"""Built-in read-only runtime tools."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from code_reader_agent.models import (
    ApiIndexEntry,
    FileMemorySummary,
    FlowIndexEntry,
    ModuleMemorySummary,
    ProjectMemory,
    SymbolIndexItem,
)
from code_reader_agent.tools import read_only
from code_reader_agent.tools.models import ToolDefinition, ToolExecutionContext


DEFAULT_TIMEOUT_MS = 5_000


def built_in_tools() -> list[ToolDefinition]:
    """Return built-in read-only tools for Ask mode."""

    return [
        _tool("list_files", "List safe project files.", "filesystem", _list_files, _schema(properties={"max_depth": {"type": "integer"}})),
        _tool("read_file", "Read a project file or excerpt.", "filesystem", _read_file, _schema(required=["relative_path"], properties=_line_read_properties())),
        _tool("read_file_chunk", "Read a line chunk from a project file.", "filesystem", _read_file, _schema(required=["path", "start_line", "end_line"], properties=_line_read_properties())),
        _tool("get_file_metadata", "Read file metadata without file content.", "filesystem", _get_file_metadata, _schema(required=["path"], properties={"path": {"type": "string"}})),
        _tool("search_keyword", "Search project files for a literal keyword.", "search", _search_keyword, _schema(required=["keyword"], properties={"keyword": {"type": "string"}, "scope": {"type": "string"}})),
        _tool("search_symbol", "Search likely source files for a symbol.", "search", _search_symbol, _schema(required=["symbol"], properties={"symbol": {"type": "string"}})),
        _tool("search_api_path", "Search API path definitions and calls.", "search", _search_api_path, _schema(required=["api_path"], properties={"api_path": {"type": "string"}})),
        _tool("search_file_by_name", "Find project files by name pattern.", "search", _search_file_by_name, _schema(required=["file_name"], properties={"file_name": {"type": "string"}, "scope": {"type": "string"}})),
        _tool("parse_dependencies", "Parse package and Java dependency metadata.", "parser", _parse_dependencies, _schema()),
        _tool("parse_package_scripts", "Parse package.json scripts.", "parser", _parse_package_scripts, _schema(properties={"file_path": {"type": "string"}})),
        _tool("parse_controller", "Parse Spring Controller endpoint candidates.", "parser", _parse_controller, _schema()),
        _tool("parse_routes", "Parse frontend route candidates.", "parser", _parse_routes, _schema()),
        _tool("parse_api_calls", "Parse frontend API call candidates.", "parser", _parse_api_calls, _schema()),
        _tool("parse_mapper", "Parse mapper/repository candidates.", "parser", _parse_mapper, _schema()),
        _tool("query_project_memory", "Query Project Memory summaries.", "index", _query_project_memory, _schema(required=["query"], properties={"query": {"type": "string"}})),
        _tool("query_code_index", "Query Code Knowledge Index.", "index", _query_code_index, _schema(required=["query"], properties={"query": {"type": "string"}})),
        _tool("query_api_index", "Query API Index.", "index", _query_api_index, _schema(required=["api_path_or_keyword"], properties={"api_path_or_keyword": {"type": "string"}})),
        _tool("query_flow_index", "Query Flow Index.", "index", _query_flow_index, _schema(required=["flow_name_or_keyword"], properties={"flow_name_or_keyword": {"type": "string"}})),
        _tool("query_symbol_index", "Query Symbol Index.", "index", _query_symbol_index, _schema(required=["symbol_name"], properties={"symbol_name": {"type": "string"}})),
    ]


def _tool(
    name: str,
    description: str,
    category: str,
    handler: Any,
    input_schema: dict[str, Any],
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        category=category,  # type: ignore[arg-type]
        permission="read",
        available_in_modes=["ask"],
        input_schema=input_schema,
        handler=handler,
        cost_level="low",
        risk_level="safe",
        timeout_ms=DEFAULT_TIMEOUT_MS,
    )


def _schema(required: list[str] | None = None, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "object", "required": required or [], "properties": properties or {}}


def _line_read_properties() -> dict[str, Any]:
    return {
        "relative_path": {"type": "string"},
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "end_line": {"type": "integer"},
        "startLine": {"type": "integer"},
        "endLine": {"type": "integer"},
    }


def _list_files(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    max_depth = args.get("max_depth")
    return read_only.list_files(context.project_path, max_depth=max_depth if isinstance(max_depth, int) else None)


def _read_file(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    relative_path = str(args.get("relative_path") or args.get("path") or "")
    return read_only.read_file(context.project_path, relative_path, line_range=_line_range(args))


def _get_file_metadata(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    root = _project_root(context.project_path)
    relative_path = str(args.get("path") or args.get("relative_path") or args.get("file_path") or "")
    target = _project_file(root, relative_path)
    stat = target.stat()
    return {
        "path": target.relative_to(root).as_posix(),
        "name": target.name,
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "language": _language_for_path(target),
    }


def _search_keyword(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    scope = str(args.get("scope")) if args.get("scope") else None
    return read_only.search_keyword(context.project_path, str(args.get("keyword") or args.get("query") or ""), scope=scope)


def _search_symbol(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.search_symbol(context.project_path, str(args.get("symbol") or args.get("symbol_name") or ""))


def _search_api_path(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.search_api_path(context.project_path, str(args.get("api_path") or args.get("apiPath") or ""))


def _search_file_by_name(args: dict[str, Any], context: ToolExecutionContext) -> list[dict[str, Any]]:
    file_name = str(args.get("file_name") or args.get("fileName") or args.get("name") or "")
    if not file_name:
        raise read_only.ReadOnlyToolError("file_name must not be empty.")
    scope = str(args.get("scope") or "")
    entries = read_only.list_files(context.project_path)
    matches = []
    for entry in entries:
        if entry.kind != "file":
            continue
        if scope and scope not in entry.path:
            continue
        if entry.name == file_name or fnmatch.fnmatch(entry.name, file_name) or file_name.lower() in entry.name.lower():
            matches.append(entry.model_dump())
    return matches[:50]


def _parse_dependencies(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.parse_dependencies(context.project_path)


def _parse_package_scripts(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    file_path = str(args.get("file_path") or args.get("path") or "package.json")
    result = read_only.read_file(context.project_path, file_path)
    try:
        data = json.loads(result.content or "{}")
    except json.JSONDecodeError as exc:
        raise read_only.ReadOnlyToolError(f"Could not parse package scripts: {file_path}") from exc
    scripts = data.get("scripts", {})
    return {"file": result.path, "scripts": scripts if isinstance(scripts, dict) else {}}


def _parse_controller(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.parse_controller(context.project_path)


def _parse_routes(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.parse_routes(context.project_path)


def _parse_api_calls(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.parse_api_calls(context.project_path)


def _parse_mapper(args: dict[str, Any], context: ToolExecutionContext) -> Any:
    return read_only.parse_mapper(context.project_path)


def _query_project_memory(args: dict[str, Any], context: ToolExecutionContext) -> list[Any]:
    memory = _require_memory(context)
    query = str(args.get("query") or "")
    values: list[Any] = [memory.project_memory, *memory.module_summaries, *memory.file_summaries]
    return _rank_index_values(query, values)[:20]


def _query_code_index(args: dict[str, Any], context: ToolExecutionContext) -> list[Any]:
    memory = _require_memory(context)
    query = str(args.get("query") or "")
    values: list[Any] = [
        *memory.module_summaries,
        *memory.file_summaries,
        *memory.api_index,
        *memory.flow_index,
        *memory.symbol_index,
        *memory.route_index,
        *memory.frontend_api_call_index,
        *memory.data_model_index,
        *memory.mapper_relations,
    ]
    return _rank_index_values(query, values)[:30]


def _query_api_index(args: dict[str, Any], context: ToolExecutionContext) -> list[ApiIndexEntry]:
    memory = _require_memory(context)
    query = str(args.get("api_path_or_keyword") or args.get("query") or "")
    return _rank_index_values(query, list(memory.api_index))[:20]


def _query_flow_index(args: dict[str, Any], context: ToolExecutionContext) -> list[FlowIndexEntry]:
    memory = _require_memory(context)
    query = str(args.get("flow_name_or_keyword") or args.get("query") or "")
    return _rank_index_values(query, list(memory.flow_index))[:20]


def _query_symbol_index(args: dict[str, Any], context: ToolExecutionContext) -> list[SymbolIndexItem]:
    memory = _require_memory(context)
    query = str(args.get("symbol_name") or args.get("query") or "")
    return _rank_index_values(query, list(memory.symbol_index))[:20]


def _require_memory(context: ToolExecutionContext) -> ProjectMemory:
    if context.project_memory is None:
        raise read_only.ReadOnlyToolError("Project memory is required for index query tools.")
    return context.project_memory


def _rank_index_values(query: str, values: list[Any]) -> list[Any]:
    lowered = query.lower()
    scored: list[tuple[int, Any]] = []
    for value in values:
        text = _index_text(value).lower()
        score = 0
        if lowered and lowered in text:
            score += 5
        score += sum(1 for token in lowered.split() if token and token in text)
        if score > 0 or not lowered:
            scored.append((score, value))
    return [value for score, value in sorted(scored, key=lambda item: item[0], reverse=True)]


def _index_text(value: Any) -> str:
    if hasattr(value, "model_dump"):
        data = value.model_dump()
        return " ".join(str(item) for item in data.values() if item)
    return str(value)


def _line_range(args: dict[str, Any]) -> tuple[int, int] | None:
    start = args.get("start_line", args.get("startLine"))
    end = args.get("end_line", args.get("endLine"))
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None


def _project_root(project_path: str) -> Path:
    root = Path(project_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise read_only.ReadOnlyToolError(f"Project path does not exist: {root}")
    return root


def _project_file(root: Path, relative_path: str) -> Path:
    if not relative_path:
        raise read_only.ReadOnlyToolError("File path must not be empty.")
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise read_only.ReadOnlyToolError("Path traversal outside the project root is not allowed.")
    if not candidate.exists() or not candidate.is_file():
        raise read_only.ReadOnlyToolError(f"File does not exist: {relative_path}")
    return candidate


def _language_for_path(path: Path) -> str:
    return {
        ".java": "Java",
        ".vue": "Vue",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".json": "JSON",
        ".xml": "XML",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".properties": "Properties",
    }.get(path.suffix, "")
