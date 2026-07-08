"""Convert raw tool outputs into compact Code Evidence."""

from __future__ import annotations

from typing import Any

from code_reader_agent.models import (
    CodeEvidence,
    EvidenceRef,
    FileTreeEntry,
    ReadFileResult,
    SearchCodeMatch,
    SearchCodeResult,
)
from code_reader_agent.tools.models import ToolResult


MAX_SNIPPET_CHARS = 2_000
MAX_EVIDENCE_ITEMS = 20


class ToolResultProcessor:
    """Process raw tool outputs before they enter Ask context."""

    def process(
        self,
        *,
        tool_name: str,
        raw_output: Any,
        args: dict[str, Any],
        reason: str,
    ) -> ToolResult:
        """Return a compact, evidence-oriented ToolResult."""

        if tool_name in {"read_file", "read_file_chunk"} and isinstance(raw_output, ReadFileResult):
            return self._read_file_result(tool_name, raw_output, reason)
        if tool_name in {"search_keyword", "search_symbol", "search_api_path", "search_file_by_name"}:
            return self._search_result(tool_name, raw_output, args, reason)
        if tool_name == "list_files":
            return self._list_files_result(tool_name, raw_output, reason)
        if tool_name == "get_file_metadata":
            return self._metadata_result(tool_name, raw_output, reason)
        if tool_name in {"parse_controller", "parse_api_calls", "parse_routes", "parse_mapper"}:
            return self._parser_result(tool_name, raw_output, reason)
        if tool_name in {"parse_dependencies", "parse_package_scripts"}:
            return self._dependency_result(tool_name, raw_output, reason)
        if tool_name.startswith("query_"):
            return self._index_result(tool_name, raw_output, reason)
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=_summarize_raw(raw_output),
        )

    def error(self, *, tool_name: str, args: dict[str, Any], reason: str, error: str) -> ToolResult:
        """Return a failed ToolResult."""

        return ToolResult(
            tool_name=tool_name,
            success=False,
            output_summary=error,
            error=error,
            warnings=[error],
        )

    def _read_file_result(self, tool_name: str, result: ReadFileResult, reason: str) -> ToolResult:
        excerpt = _trim_snippet(result.content, MAX_SNIPPET_CHARS)
        reference = EvidenceRef(
            path=result.path,
            reason=reason,
            source=tool_name,
            start_line=result.start_line,
            end_line=result.end_line,
            excerpt=excerpt,
        )
        evidence = CodeEvidence(
            source="tool",
            file_path=result.path,
            content_summary=f"Read lines {result.start_line}-{result.end_line}.",
            code_snippet=excerpt,
            relevance_reason=reason,
        )
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=result,
            output_summary=f"Read lines {result.start_line}-{result.end_line}.",
            evidence=[evidence],
            references=[reference],
            related_files=[result.path],
            warnings=result.warnings,
        )

    def _search_result(self, tool_name: str, raw_output: Any, args: dict[str, Any], reason: str) -> ToolResult:
        if isinstance(raw_output, SearchCodeResult):
            matches = raw_output.matches
            warnings = raw_output.warnings
            summary = f"Found {len(matches)} matches."
            related_files = [match.path for match in matches]
            api = str(args.get("api_path") or "") or None
            symbol = str(args.get("symbol") or "") or None
            references = [_match_reference(tool_name, match, reason) for match in matches]
            evidence = [
                CodeEvidence(
                    source="tool",
                    file_path=match.path,
                    symbol=symbol,
                    api=api,
                    content_summary=f"Matched line {match.line_number}.",
                    code_snippet=match.line,
                    relevance_reason=reason,
                )
                for match in matches[:MAX_EVIDENCE_ITEMS]
            ]
            return ToolResult(
                tool_name=tool_name,
                success=True,
                raw_output=raw_output,
                output_summary=summary,
                evidence=evidence,
                references=references,
                related_files=related_files,
                warnings=warnings,
            )

        items = _as_list(raw_output)
        related_files = [str(item.get("path") or "") for item in items if isinstance(item, dict)]
        evidence = [
            CodeEvidence(
                source="tool",
                file_path=str(item.get("path") or ""),
                content_summary=f"Matched file name {item.get('name') or item.get('path')}.",
                relevance_reason=reason,
            )
            for item in items[:MAX_EVIDENCE_ITEMS]
            if isinstance(item, dict)
        ]
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=f"Found {len(items)} file candidates.",
            evidence=evidence,
            related_files=related_files,
        )

    def _list_files_result(self, tool_name: str, raw_output: Any, reason: str) -> ToolResult:
        entries = _as_list(raw_output)
        notes = [f"文件树包含 {len(entries)} 个条目。"]
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=f"Listed {len(entries)} entries.",
            notes=notes,
        )

    def _metadata_result(self, tool_name: str, raw_output: Any, reason: str) -> ToolResult:
        path = str(raw_output.get("path") or "") if isinstance(raw_output, dict) else ""
        evidence = [
            CodeEvidence(
                source="tool",
                file_path=path,
                content_summary=_metadata_summary(raw_output),
                relevance_reason=reason,
            )
        ] if path else []
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=_metadata_summary(raw_output),
            evidence=evidence,
            related_files=[path] if path else [],
        )

    def _parser_result(self, tool_name: str, raw_output: Any, reason: str) -> ToolResult:
        items = _as_list(raw_output)
        related_files = _files_from_parser_items(tool_name, items)
        evidence = [_parser_evidence(tool_name, item, reason) for item in items[:MAX_EVIDENCE_ITEMS] if isinstance(item, dict)]
        evidence = [item for item in evidence if item is not None]
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=_parser_summary(tool_name, len(items)),
            evidence=evidence,
            related_files=related_files,
            implementation_path=related_files,
        )

    def _dependency_result(self, tool_name: str, raw_output: Any, reason: str) -> ToolResult:
        related_files = []
        if isinstance(raw_output, dict):
            related_files = [
                path
                for path in ["package.json", "pom.xml", "build.gradle", "build.gradle.kts", *[str(item) for item in raw_output.get("java_config_files", [])]]
                if path
            ]
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary="Parsed dependency metadata.",
            related_files=related_files,
            notes=[_dependency_note(raw_output)],
        )

    def _index_result(self, tool_name: str, raw_output: Any, reason: str) -> ToolResult:
        items = _as_list(raw_output)
        evidence = [_index_evidence(item, reason) for item in items[:MAX_EVIDENCE_ITEMS]]
        evidence = [item for item in evidence if item is not None]
        related_files = [item.file_path for item in evidence if item.file_path]
        return ToolResult(
            tool_name=tool_name,
            success=True,
            raw_output=raw_output,
            output_summary=f"Found {len(items)} index candidates.",
            evidence=evidence,
            related_files=related_files,
        )


def _match_reference(tool_name: str, match: SearchCodeMatch, reason: str) -> EvidenceRef:
    return EvidenceRef(
        path=match.path,
        reason=reason,
        source=tool_name,
        start_line=match.line_number,
        end_line=match.line_number,
        excerpt=match.line,
    )


def _parser_evidence(tool_name: str, item: dict[str, Any], reason: str) -> CodeEvidence | None:
    if tool_name == "parse_controller":
        file_path = str(item.get("backend_file") or "")
        return CodeEvidence(
            source="tool",
            file_path=file_path or None,
            api=str(item.get("path") or "") or None,
            symbol=str(item.get("backend_method") or "") or None,
            content_summary=f"{item.get('method') or 'UNKNOWN'} {item.get('path') or file_path}",
            relevance_reason=reason,
        )
    if tool_name == "parse_api_calls":
        file_path = str(item.get("file") or "")
        return CodeEvidence(
            source="tool",
            file_path=file_path or None,
            api=str(item.get("path") or "") or None,
            content_summary=f"{item.get('method') or 'UNKNOWN'} {item.get('path')}",
            relevance_reason=reason,
        )
    if tool_name == "parse_routes":
        return CodeEvidence(
            source="tool",
            file_path=str(item.get("file") or "") or None,
            content_summary=f"route={item.get('path')}",
            relevance_reason=reason,
        )
    if tool_name == "parse_mapper":
        return CodeEvidence(
            source="tool",
            file_path=str(item.get("path") or "") or None,
            content_summary=f"mapper={item.get('kind')}",
            relevance_reason=reason,
        )
    return None


def _index_evidence(item: Any, reason: str) -> CodeEvidence | None:
    if hasattr(item, "path"):
        return CodeEvidence(
            source="memory",
            file_path=getattr(item, "backend_file", None) or getattr(item, "frontend_call_file", None) or None,
            api=str(getattr(item, "path", "") or "") or None,
            content_summary=_model_summary(item),
            relevance_reason=reason,
        )
    if hasattr(item, "file_path"):
        return CodeEvidence(
            source="memory",
            file_path=getattr(item, "file_path", None),
            symbol=str(getattr(item, "name", "") or "") or None,
            content_summary=_model_summary(item),
            relevance_reason=reason,
        )
    if hasattr(item, "evidence_files"):
        evidence_files = list(getattr(item, "evidence_files", []) or [])
        return CodeEvidence(
            source="memory",
            file_path=evidence_files[0] if evidence_files else None,
            content_summary=_model_summary(item),
            relevance_reason=reason,
        )
    if hasattr(item, "responsibility"):
        return CodeEvidence(
            source="memory",
            file_path=getattr(item, "path", None),
            content_summary=_model_summary(item),
            relevance_reason=reason,
        )
    return None


def _files_from_parser_items(tool_name: str, items: list[Any]) -> list[str]:
    files: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if tool_name == "parse_controller":
            files.append(str(item.get("backend_file") or ""))
        elif tool_name in {"parse_api_calls", "parse_routes"}:
            files.append(str(item.get("file") or ""))
        elif tool_name == "parse_mapper":
            files.append(str(item.get("path") or ""))
    return _dedupe_strings(files)


def _parser_summary(tool_name: str, count: int) -> str:
    labels = {
        "parse_controller": "controller endpoints",
        "parse_api_calls": "frontend API calls",
        "parse_routes": "route candidates",
        "parse_mapper": "mapping candidates",
    }
    return f"Found {count} {labels.get(tool_name, 'items')}."


def _dependency_note(raw_output: Any) -> str:
    if not isinstance(raw_output, dict):
        return "依赖摘要不可用。"
    frontend = raw_output.get("frontend_dependencies")
    java = raw_output.get("java_dependencies")
    scripts = raw_output.get("scripts")
    return (
        f"依赖摘要: frontend={len(frontend) if isinstance(frontend, dict) else 0}, "
        f"java={len(java) if isinstance(java, dict) else 0}, "
        f"scripts={len(scripts) if isinstance(scripts, dict) else 0}。"
    )


def _metadata_summary(raw_output: Any) -> str:
    if not isinstance(raw_output, dict):
        return "Read file metadata."
    return f"{raw_output.get('path')}: {raw_output.get('language') or 'unknown'}, {raw_output.get('size_bytes')} bytes."


def _model_summary(item: Any) -> str:
    if hasattr(item, "model_dump"):
        data = item.model_dump()
        parts = [f"{key}={value}" for key, value in data.items() if value not in (None, "", [], {})]
        return " ".join(parts[:6])
    return str(item)


def _summarize_raw(raw_output: Any) -> str:
    if isinstance(raw_output, list):
        return f"Returned {len(raw_output)} items."
    if isinstance(raw_output, dict):
        return f"Returned {len(raw_output)} fields."
    return "Tool returned output."


def _as_list(raw_output: Any) -> list[Any]:
    if isinstance(raw_output, list):
        return raw_output
    if isinstance(raw_output, tuple):
        return list(raw_output)
    if isinstance(raw_output, SearchCodeResult):
        return list(raw_output.matches)
    if isinstance(raw_output, dict) and isinstance(raw_output.get("items"), list):
        return list(raw_output["items"])
    return []


def _trim_snippet(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}\n...[truncated]"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
