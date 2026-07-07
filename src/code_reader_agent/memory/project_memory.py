"""Project-level structured memory for Ask mode."""

from __future__ import annotations

from code_reader_agent.local_state import project_id_for_path
from code_reader_agent.models import (
    ApiIndexEntry,
    FileMemorySummary,
    FlowIndexEntry,
    ModuleMemorySummary,
    ProjectManual,
    ProjectMemory,
    ProjectMemoryOverview,
    RepoMap,
)
from code_reader_agent.tools.read_only import parse_api_calls, parse_controller


def build_project_memory(repo_map: RepoMap, project_manual: ProjectManual | None = None) -> ProjectMemory:
    """Build reusable Ask mode memory from deterministic Repo Map data."""

    project_memory = ProjectMemory(
        project_id=project_id_for_path(repo_map.project_path),
        project_name=repo_map.project_name,
        project_path=repo_map.project_path,
        project_memory=ProjectMemoryOverview(
            positioning=_project_positioning(repo_map, project_manual),
            tech_stack=[item.name for item in repo_map.stack_explanations] or [item.name for item in repo_map.detected_stack],
            startup_commands=_startup_commands(repo_map),
            modules=[item.name for item in repo_map.modules],
        ),
        module_summaries=_module_summaries(repo_map),
        file_summaries=_file_summaries(repo_map),
    )
    project_memory.api_index = _api_index(repo_map)
    project_memory.flow_index = _flow_index(repo_map, project_memory.api_index)
    return project_memory


def _project_positioning(repo_map: RepoMap, project_manual: ProjectManual | None) -> str:
    if project_manual and project_manual.overview:
        return project_manual.overview.one_liner
    if repo_map.project_summary:
        return repo_map.project_summary.one_liner
    return f"{repo_map.project_name} 是一个已扫描的本地代码库；当前缺少更明确的项目说明证据。"


def _startup_commands(repo_map: RepoMap) -> list[str]:
    commands = [f"{name}: {command}" for name, command in sorted(repo_map.run_scripts.items())]
    if repo_map.java_build_tool == "maven":
        commands.append("maven: mvn spring-boot:run 或 mvn test 作为候选命令，需要本地确认。")
    if repo_map.java_build_tool == "gradle":
        commands.append("gradle: ./gradlew bootRun 或 ./gradlew test 作为候选命令，需要本地确认。")
    return commands


def _module_summaries(repo_map: RepoMap) -> list[ModuleMemorySummary]:
    summaries: list[ModuleMemorySummary] = []
    files_by_path = {item.path: item for item in repo_map.files}
    for module in sorted(repo_map.modules, key=lambda item: (item.reading_priority, item.name)):
        related_files = _dedupe_strings([*module.entry_files, *module.key_files])
        controller_files: list[str] = []
        service_files: list[str] = []
        view_files: list[str] = []
        api_files: list[str] = []
        for path in related_files:
            role = files_by_path.get(path).role if path in files_by_path else ""
            if role == "controller":
                controller_files.append(path)
            if role == "service":
                service_files.append(path)
            if role == "view":
                view_files.append(path)
            if role == "api_client":
                api_files.append(path)
        summaries.append(
            ModuleMemorySummary(
                name=module.name,
                responsibility=module.responsibility,
                entry_files=module.entry_files,
                controller_files=controller_files,
                service_files=service_files,
                view_files=view_files,
                api_files=api_files,
                related_files=related_files,
            )
        )
    return summaries


def _file_summaries(repo_map: RepoMap) -> list[FileMemorySummary]:
    return [
        FileMemorySummary(
            path=file.path,
            responsibility=file.summary,
            role=file.role,
            symbols=file.symbols,
        )
        for file in sorted(repo_map.files, key=lambda item: (-item.importance_score, item.path))
    ]


def _api_index(repo_map: RepoMap) -> list[ApiIndexEntry]:
    entries_by_key: dict[tuple[str, str | None, str | None], ApiIndexEntry] = {}
    for endpoint in _safe_parse_controller(repo_map.project_path):
        path = str(endpoint.get("path") or "")
        backend_file = str(endpoint.get("backend_file") or "")
        method = endpoint.get("method")
        key = (path, str(method) if method else None, backend_file)
        entries_by_key[key] = ApiIndexEntry(
            path=path or backend_file,
            method=str(method) if method else None,
            backend_method=str(endpoint.get("backend_method") or "") or None,
            backend_file=backend_file or None,
        )

    frontend_calls = _safe_parse_api_calls(repo_map.project_path)
    for call in frontend_calls:
        call_path = str(call.get("path") or "")
        if not call_path:
            continue
        matched = _find_api_entry(entries_by_key.values(), call_path)
        if matched:
            matched.frontend_calls = _dedupe_strings([*matched.frontend_calls, str(call.get("file") or "")])
            continue
        key = (call_path, str(call.get("method") or "") or None, None)
        entries_by_key.setdefault(
            key,
            ApiIndexEntry(
                path=call_path,
                method=str(call.get("method") or "") or None,
                frontend_calls=[str(call.get("file") or "")],
            ),
        )

    for path in repo_map.api_endpoints:
        key = (path, None, path)
        entries_by_key.setdefault(key, ApiIndexEntry(path=path, backend_file=path if path.endswith(".java") else None))
    return list(entries_by_key.values())[:120]


def _flow_index(repo_map: RepoMap, api_index: list[ApiIndexEntry]) -> list[FlowIndexEntry]:
    flows: list[FlowIndexEntry] = []
    auth_files = _dedupe_strings(repo_map.auth_flows[:12])
    if auth_files:
        flows.append(
            FlowIndexEntry(
                name="认证/登录流程候选",
                kind="auth",
                steps=auth_files,
                evidence_files=auth_files,
                confidence=0.55,
            )
        )
    api_files = _dedupe_strings(
        [
            *[entry.backend_file for entry in api_index if entry.backend_file],
            *[call for entry in api_index for call in entry.frontend_calls],
        ]
    )
    if api_files:
        flows.append(
            FlowIndexEntry(
                name="接口调用链候选",
                kind="api",
                steps=api_files[:16],
                evidence_files=api_files[:16],
                confidence=0.5,
            )
        )
    for path in repo_map.api_flows[:10]:
        flows.append(
            FlowIndexEntry(
                name=path,
                kind="candidate",
                steps=[path],
                evidence_files=[path],
                confidence=0.35,
            )
        )
    return flows


def _safe_parse_controller(project_path: str) -> list[dict[str, object]]:
    try:
        return parse_controller(project_path)
    except Exception:
        return []


def _safe_parse_api_calls(project_path: str) -> list[dict[str, object]]:
    try:
        return parse_api_calls(project_path)
    except Exception:
        return []


def _find_api_entry(entries: object, call_path: str) -> ApiIndexEntry | None:
    normalized_call = call_path.strip("/")
    for entry in entries:
        if not isinstance(entry, ApiIndexEntry):
            continue
        normalized_entry = entry.path.strip("/")
        if not normalized_entry:
            continue
        if normalized_entry == normalized_call or normalized_entry.endswith(normalized_call) or normalized_call.endswith(normalized_entry):
            return entry
    return None


def _dedupe_strings(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
