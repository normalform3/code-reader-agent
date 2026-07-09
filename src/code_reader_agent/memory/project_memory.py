"""Project-level structured memory for Ask mode."""

from __future__ import annotations

from hashlib import sha1

from code_reader_agent.local_state import project_id_for_path
from code_reader_agent.models import (
    ApiIndexEntry,
    DirectoryMemorySummary,
    FileMemorySummary,
    FlowIndexEntry,
    ModuleMemorySummary,
    ProjectManual,
    ProjectMemory,
    ProjectMemoryOverview,
    RepoMap,
    SymbolIndexItem,
)
from code_reader_agent.skills.registry import default_skill_registry
from code_reader_agent.tools.read_only import parse_api_calls, parse_controller


def build_project_memory(repo_map: RepoMap, project_manual: ProjectManual | None = None, *, include_skills: bool = True) -> ProjectMemory:
    """Build reusable Ask mode memory from deterministic Repo Map data."""

    api_index = _api_index(repo_map)
    project_memory = ProjectMemory(
        project_id=project_id_for_path(repo_map.project_path),
        project_name=repo_map.project_name,
        project_path=repo_map.project_path,
        project_memory=ProjectMemoryOverview(
            positioning=_project_positioning(repo_map, project_manual),
            description=_project_description(repo_map, project_manual),
            project_type=_project_type(repo_map),
            tech_stack=[item.name for item in repo_map.stack_explanations] or [item.name for item in repo_map.detected_stack],
            startup_commands=_startup_commands(repo_map),
            entry_points=[entry.path for entry in repo_map.entrypoints],
            build_tools=_build_tools(repo_map),
            config_files=_config_files(repo_map),
            external_dependencies=_external_dependencies(repo_map),
            modules=_memory_module_names(repo_map, project_manual),
            directory_summary=[
                DirectoryMemorySummary(path=item.path, role=item.role)
                for item in repo_map.directory_insights[:24]
            ],
        ),
        module_summaries=_module_summaries(repo_map, api_index, project_manual),
        file_summaries=_file_summaries(repo_map, api_index),
        api_index=api_index,
    )
    project_memory.flow_index = _flow_index(repo_map, project_memory.api_index)
    project_memory.symbol_index = _symbol_index(project_memory.file_summaries)
    if include_skills:
        project_memory = default_skill_registry().build_indexes(repo_map, project_memory)
    return project_memory


def _project_positioning(repo_map: RepoMap, project_manual: ProjectManual | None) -> str:
    if project_manual and project_manual.manual_overview and project_manual.manual_overview.one_liner:
        return project_manual.manual_overview.one_liner
    if project_manual and project_manual.overview:
        return project_manual.overview.one_liner
    if repo_map.project_summary:
        return repo_map.project_summary.one_liner
    return f"{repo_map.project_name} 是一个已扫描的本地代码库；当前缺少更明确的项目说明证据。"


def _project_description(repo_map: RepoMap, project_manual: ProjectManual | None) -> str:
    if project_manual and project_manual.manual_overview and project_manual.manual_overview.one_liner:
        return project_manual.manual_overview.one_liner
    if project_manual and project_manual.overview:
        return project_manual.overview.problem or project_manual.overview.one_liner
    if repo_map.project_summary:
        return repo_map.project_summary.problem or repo_map.project_summary.one_liner
    return ""


def _project_type(repo_map: RepoMap) -> str:
    stack = {item.name for item in repo_map.detected_stack}
    if stack & {"Vue", "Vite"} and stack & {"Spring Boot", "Spring Web", "Java"}:
        return "frontend_backend_web"
    if stack & {"Spring Boot", "Spring Web", "Java"}:
        return "java_web"
    if stack & {"Vue", "Vite"}:
        return "frontend_web"
    return "unknown"


def _startup_commands(repo_map: RepoMap) -> list[str]:
    commands = [f"{name}: {command}" for name, command in sorted(repo_map.run_scripts.items())]
    if repo_map.java_build_tool == "maven":
        commands.append("maven: mvn spring-boot:run 或 mvn test 作为候选命令，需要本地确认。")
    if repo_map.java_build_tool == "gradle":
        commands.append("gradle: ./gradlew bootRun 或 ./gradlew test 作为候选命令，需要本地确认。")
    return commands


def _build_tools(repo_map: RepoMap) -> list[str]:
    tools: list[str] = []
    if repo_map.package_manager:
        tools.append(repo_map.package_manager)
    if repo_map.java_build_tool:
        tools.append(repo_map.java_build_tool)
    return _dedupe_strings(tools)


def _config_files(repo_map: RepoMap) -> list[str]:
    config_roles = {"config", "build_config"}
    return _dedupe_strings(
        [
            entry.path
            for entry in repo_map.files
            if entry.role in config_roles
            or entry.path.endswith(("package.json", "pom.xml", "build.gradle", "build.gradle.kts", ".yml", ".yaml", ".properties"))
        ]
    )[:40]


def _external_dependencies(repo_map: RepoMap) -> list[str]:
    return [name for name in sorted(repo_map.dependencies) if name][:80]


def _memory_module_names(repo_map: RepoMap, project_manual: ProjectManual | None) -> list[str]:
    if project_manual and project_manual.core_modules:
        return [item.name for item in project_manual.core_modules]
    return [item.name for item in repo_map.modules]


def _module_summaries(
    repo_map: RepoMap,
    api_index: list[ApiIndexEntry],
    project_manual: ProjectManual | None = None,
) -> list[ModuleMemorySummary]:
    if project_manual and project_manual.core_modules:
        return [
            ModuleMemorySummary(
                name=module.name,
                responsibility=module.responsibility,
                related_files=module.related_files,
                related_apis=module.api_candidates,
            )
            for module in project_manual.core_modules
        ]
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
                role=module.type,
                entry_files=module.entry_files,
                controller_files=controller_files,
                service_files=service_files,
                view_files=view_files,
                api_files=api_files,
                related_files=related_files,
                related_apis=_apis_for_files(api_index, related_files),
                related_entities=[path for path in related_files if files_by_path.get(path) and files_by_path[path].role in {"entity", "dto", "vo"}],
            )
        )
    return summaries


def _file_summaries(repo_map: RepoMap, api_index: list[ApiIndexEntry]) -> list[FileMemorySummary]:
    return [
        FileMemorySummary(
            path=file.path,
            responsibility=file.summary,
            role=file.role,
            language=file.language or "",
            symbols=file.symbols or _fallback_symbols(file.path),
            related_apis=_apis_for_files(api_index, [file.path]),
            hash=_summary_hash(file.path, file.role, file.summary, file.symbols or _fallback_symbols(file.path)),
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
            matched.frontend_call_file = matched.frontend_calls[0] if matched.frontend_calls else None
            continue
        key = (call_path, str(call.get("method") or "") or None, None)
        entries_by_key.setdefault(
            key,
            ApiIndexEntry(
                path=call_path,
                method=str(call.get("method") or "") or None,
                frontend_call_file=str(call.get("file") or "") or None,
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
                description="基于文件名、路径和 Repo Map 识别出的认证/登录流程候选。",
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
                description="基于 API Index 关联出的前端调用与后端处理文件候选。",
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
                description="Repo Map 识别出的流程候选，需要 Ask 模式继续读取真实代码确认。",
                steps=[path],
                evidence_files=[path],
                confidence=0.35,
            )
        )
    return flows


def _symbol_index(file_summaries: list[FileMemorySummary]) -> list[SymbolIndexItem]:
    index: list[SymbolIndexItem] = []
    for file in file_summaries:
        for symbol in file.symbols:
            index.append(
                SymbolIndexItem(
                    name=symbol,
                    kind=_symbol_kind(file.path, file.role, symbol),
                    file_path=file.path,
                    summary=file.responsibility,
                )
            )
    return index[:300]


def _symbol_kind(path: str, role: str, symbol: str) -> str:
    if path.endswith(".vue"):
        return "component"
    if path.endswith(".java") and symbol[:1].isupper():
        return "class"
    if path.endswith((".ts", ".tsx")) and role in {"component", "view"}:
        return "component"
    if symbol[:1].isupper():
        return "class"
    return "function"


def _apis_for_files(api_index: list[ApiIndexEntry], files: list[str]) -> list[str]:
    wanted = set(files)
    apis: list[str] = []
    for entry in api_index:
        if entry.backend_file in wanted or any(path in wanted for path in entry.frontend_calls):
            apis.append(entry.path)
    return _dedupe_strings(apis)


def _summary_hash(path: str, role: str, summary: str, symbols: list[str]) -> str:
    payload = "\n".join([path, role, summary, *symbols])
    return sha1(payload.encode("utf-8")).hexdigest()[:12]


def _fallback_symbols(path: str) -> list[str]:
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if path.endswith((".java", ".vue", ".ts", ".tsx", ".js", ".jsx")) and stem:
        return [stem]
    return []


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
