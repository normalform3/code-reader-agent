"""Phase 4 single-agent project interpretation flow.

The first implementation prepares an evidence-grounded prompt and returns a
deterministic fallback interpretation. A future LLM provider can consume the
same prompt messages without changing the API contract.
"""

from __future__ import annotations

from collections.abc import Iterable

from code_reader_agent.models import (
    Entrypoint,
    EvidenceRef,
    ProjectInterpretationResult,
    ProjectScanResult,
    PromptMessage,
    ReadingPathItem,
    ToolCallRecord,
)
from code_reader_agent.prompts import (
    PROJECT_INTERPRETER_PROMPT_VERSION,
    PROJECT_INTERPRETER_SYSTEM_PROMPT,
    build_project_interpreter_user_prompt,
)
from code_reader_agent.scanner import scan_project
from code_reader_agent.tools.read_only import ReadOnlyToolError, read_file, search_code


PROJECT_OVERVIEW_SKILL = "project_overview_skill"
SETUP_ANALYSIS_SKILL = "setup_analysis_skill"
FRONTEND_ANALYSIS_SKILL = "frontend_analysis_skill"


def interpret_project(project_path: str, question: str | None = None) -> ProjectInterpretationResult:
    """Scan a project and produce a Phase 4 single-agent interpretation."""

    effective_question = question or "这个项目是干什么的？我应该怎么运行，并从哪些文件开始看？"
    scan = scan_project(project_path)
    return interpret_scan(scan, effective_question)


def interpret_scan(scan: ProjectScanResult, question: str) -> ProjectInterpretationResult:
    """Interpret an existing scan result without reading more project files."""

    skill = _route_skill(question)
    evidence, read_files, evidence_tool_calls = _build_evidence(scan, skill)
    flow_tool_calls: list[ToolCallRecord] = []
    if _looks_like_flow_question(question):
        flow_evidence, flow_calls = _find_flow_candidates(scan)
        evidence = _dedupe_evidence([*evidence, *flow_evidence])
        flow_tool_calls.extend(flow_calls)
    reading_path = _build_reading_path_for_skill(scan, skill)
    scan_context = _format_scan_context(scan, evidence, reading_path)
    prompt_messages = [
        PromptMessage(role="system", content=PROJECT_INTERPRETER_SYSTEM_PROMPT),
        PromptMessage(
            role="user",
            content=build_project_interpreter_user_prompt(scan_context=scan_context, question=question),
        ),
    ]

    warnings = list(scan.warnings)
    if not scan.package.found and not scan.java_build.found:
        warnings.append("缺少 package.json，项目用途和启动方式只能基于文件树低置信度推断。")
    if not reading_path:
        warnings.append("未找到标准 Vue/Vite 或 Java 入口文件，建议后续增加搜索型工具读取 README 或源码入口。")
    if _looks_like_flow_question(question):
        warnings.append("当前只识别登录/API 相关候选文件，尚未实现完整调用链追踪。")

    return ProjectInterpretationResult(
        project_name=scan.project_name,
        question=question,
        skill=skill,
        prompt_version=PROJECT_INTERPRETER_PROMPT_VERSION,
        prompt_messages=prompt_messages,
        overview=_build_skill_overview(scan, skill),
        setup_summary=_build_setup_summary(scan),
        reading_path=reading_path,
        evidence=evidence,
        tool_calls=_build_tool_calls(scan, evidence, [*evidence_tool_calls, *flow_tool_calls]),
        read_files=read_files,
        suggested_questions=_suggest_questions(scan, skill),
        warnings=warnings,
    )


def _route_skill(question: str) -> str:
    normalized = question.lower()
    if any(keyword in normalized for keyword in ("怎么运行", "启动", "构建", "build", "dev", "run", "install", "setup")):
        return SETUP_ANALYSIS_SKILL
    if any(keyword in normalized for keyword in ("前端", "页面", "组件", "路由", "frontend", "view", "component", "router")):
        return FRONTEND_ANALYSIS_SKILL
    return PROJECT_OVERVIEW_SKILL


def _looks_like_flow_question(question: str) -> bool:
    normalized = question.lower()
    return any(keyword in normalized for keyword in ("登录", "认证", "权限", "接口", "api", "auth", "login", "token"))


def _build_overview(scan: ProjectScanResult) -> str:
    stack_names = [tag.name for tag in scan.detected_stack]
    if not stack_names:
        return f"{scan.project_name} 是一个本地项目；当前扫描未找到足够的技术栈证据。"

    stack_summary = "、".join(stack_names)
    return f"{scan.project_name} 看起来是一个基于 {stack_summary} 的项目。该判断来自 package.json、入口文件和文件树扫描。"


def _build_skill_overview(scan: ProjectScanResult, skill: str) -> str:
    if skill == SETUP_ANALYSIS_SKILL:
        stack_summary = "、".join(tag.name for tag in scan.detected_stack) or "未知技术栈"
        return f"{scan.project_name} 的运行方式优先基于 package.json scripts 和 Java 构建配置判断；当前识别到 {stack_summary}。"
    if skill == FRONTEND_ANALYSIS_SKILL:
        frontend_files = _frontend_candidate_paths(scan)
        if frontend_files:
            return f"{scan.project_name} 的前端结构可先从入口、路由、页面和组件候选文件理解。"
        return f"{scan.project_name} 当前未扫描到标准 Vue/Vite 前端结构。"
    return _build_overview(scan)


def _build_setup_summary(scan: ProjectScanResult) -> str:
    scripts = scan.package.scripts
    if not scripts and not scan.java_build.found:
        return "未在 package.json 中找到 scripts，当前无法给出确定的启动或构建命令。"
    if not scripts and scan.java_build.found:
        return _build_java_setup_summary(scan)

    package_manager = scan.package.package_manager or "npm"
    parts: list[str] = [f"建议使用 {package_manager} 安装依赖。"]
    if "dev" in scripts:
        parts.append(f"开发启动命令来自 package.json scripts：{package_manager} run dev。")
    if "build" in scripts:
        parts.append(f"构建命令来自 package.json scripts：{package_manager} run build。")
    if "preview" in scripts:
        parts.append(f"预览命令来自 package.json scripts：{package_manager} run preview。")
    if len(parts) == 1:
        available = "、".join(sorted(scripts))
        parts.append(f"可用 scripts：{available}。")
    if scan.java_build.found:
        parts.append(_build_java_setup_summary(scan))
    return " ".join(parts)


def _build_java_setup_summary(scan: ProjectScanResult) -> str:
    java_build = scan.java_build
    if java_build.build_tool == "maven":
        return "检测到 Maven 项目；可优先尝试 mvn spring-boot:run 运行，使用 mvn test 执行测试。该命令基于 pom.xml 和 Spring Boot/Maven 约定，需要用户在本地确认。"
    if java_build.build_tool == "gradle":
        return "检测到 Gradle 项目；可优先尝试 ./gradlew bootRun 运行，使用 ./gradlew test 执行测试。该命令基于 build.gradle 和 Spring Boot/Gradle 约定，需要用户在本地确认。"
    return "检测到 Java 项目结构，但未找到 Maven 或 Gradle 构建配置，当前无法给出确定启动命令。"


def _build_reading_path(entrypoints: Iterable[Entrypoint]) -> list[ReadingPathItem]:
    priority = {
        "vite_config": "先看构建和插件配置，确认项目如何被 Vite 启动。",
        "app_entry": "再看应用入口，确认 Vue 应用如何挂载和注入插件。",
        "root_component": "接着看根组件，理解页面骨架。",
        "router": "最后看路由入口，梳理页面组织和导航结构。",
        "java_config": "先看应用配置，确认运行环境、服务名和外部依赖配置。",
        "java_app_entry": "再看 Java 应用入口，确认 Spring Boot 应用如何启动。",
        "java_controller": "接着看 Controller，理解外部接口入口。",
        "java_service": "继续看 Service，理解核心业务逻辑边界。",
        "java_repository": "最后看 Repository，理解数据访问边界。",
        "java_mapper": "最后看 Mapper，理解数据访问边界。",
    }
    sorted_entrypoints = sorted(
        entrypoints,
        key=lambda item: (
            list(priority).index(item.kind) if item.kind in priority else len(priority),
            item.path,
        ),
    )
    return [
        ReadingPathItem(order=index, path=entrypoint.path, reason=priority.get(entrypoint.kind, "关键入口文件。"))
        for index, entrypoint in enumerate(sorted_entrypoints, start=1)
    ]


def _build_reading_path_for_skill(scan: ProjectScanResult, skill: str) -> list[ReadingPathItem]:
    if skill == FRONTEND_ANALYSIS_SKILL:
        paths = _frontend_candidate_paths(scan)
        reasons = {
            "vite.config": "先看构建配置，确认 Vite 插件和别名。",
            "src/main": "再看应用入口，确认 Vue 应用如何挂载。",
            "src/App.vue": "接着看根组件，理解页面骨架。",
            "router": "继续看路由文件，梳理页面组织。",
            "views": "再看页面目录，理解主要屏幕。",
            "components": "最后看组件目录，理解复用 UI 边界。",
        }
        return [
            ReadingPathItem(order=index, path=path, reason=_frontend_reason(path, reasons))
            for index, path in enumerate(paths, start=1)
        ]
    return _build_reading_path(scan.entrypoints)


def _frontend_candidate_paths(scan: ProjectScanResult) -> list[str]:
    priority_paths: list[str] = []
    entrypoint_paths = [entrypoint.path for entrypoint in scan.entrypoints]
    for path in ("vite.config.ts", "vite.config.js", "src/main.ts", "src/main.js", "src/App.vue", "src/router/index.ts", "src/router/index.js"):
        if path in entrypoint_paths:
            priority_paths.append(path)

    candidate_files = [
        entry.path
        for entry in scan.file_tree
        if entry.kind == "file"
        and (
            entry.path.startswith("src/views/")
            or entry.path.startswith("src/pages/")
            or entry.path.startswith("src/components/")
            or "/router/" in entry.path
        )
    ]
    return _dedupe_paths([*priority_paths, *sorted(candidate_files)[:12]])


def _frontend_reason(path: str, reasons: dict[str, str]) -> str:
    if path.startswith("vite.config"):
        return reasons["vite.config"]
    if path.startswith("src/main"):
        return reasons["src/main"]
    if path == "src/App.vue":
        return reasons["src/App.vue"]
    if "/router/" in path:
        return reasons["router"]
    if path.startswith(("src/views/", "src/pages/")):
        return reasons["views"]
    if path.startswith("src/components/"):
        return reasons["components"]
    return "前端结构候选文件。"


def _build_evidence(scan: ProjectScanResult, skill: str) -> tuple[list[EvidenceRef], list[str], list[ToolCallRecord]]:
    evidence: list[EvidenceRef] = []
    read_files: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    if scan.package.found:
        item, call = _evidence_from_file(scan.project_path, "package.json", "项目名称、依赖、包管理器和 scripts。", "read_config")
        evidence.append(item)
        tool_calls.append(call)
        read_files.append("package.json")
    if scan.java_build.found:
        path = _java_build_path(scan)
        if path.startswith("<"):
            evidence.append(EvidenceRef(path=path, reason="Java 构建工具、项目坐标、依赖和配置文件。", source="read_config"))
        else:
            item, call = _evidence_from_file(scan.project_path, path, "Java 构建工具、项目坐标、依赖和配置文件。", "read_config")
            evidence.append(item)
            tool_calls.append(call)
            read_files.append(path)

    for path, reason, source in _skill_evidence_targets(scan, skill):
        item, call = _evidence_from_file(scan.project_path, path, reason, source)
        evidence.append(item)
        tool_calls.append(call)
        read_files.append(path)

    for tag in scan.detected_stack:
        evidence.append(EvidenceRef(path=_evidence_path_from_source(tag.source), reason=f"识别技术栈：{tag.name}。", source="detect_framework"))

    return _dedupe_evidence(evidence), _dedupe_paths(read_files), tool_calls


def _skill_evidence_targets(scan: ProjectScanResult, skill: str) -> list[tuple[str, str, str]]:
    if skill == FRONTEND_ANALYSIS_SKILL:
        return [(path, "前端结构和阅读路径候选文件。", "frontend_analysis_skill") for path in _frontend_candidate_paths(scan)[:8]]
    return [(entrypoint.path, f"检测到 {entrypoint.kind} 入口文件。", "find_entrypoints") for entrypoint in scan.entrypoints]


def _evidence_from_file(project_path: str, path: str, reason: str, source: str) -> tuple[EvidenceRef, ToolCallRecord]:
    try:
        result = read_file(project_path, path, line_range=(1, 40))
    except (ReadOnlyToolError, ValueError) as exc:
        return (
            EvidenceRef(path=path, reason=reason, source=source),
            ToolCallRecord(
                tool_name="read_file",
                input_summary=path,
                output_summary="读取失败，保留路径级证据。",
                status="error",
                error=str(exc),
            ),
        )
    return (
        EvidenceRef(
            path=path,
            reason=reason,
            source=source,
            start_line=result.start_line,
            end_line=result.end_line,
            excerpt=result.content,
        ),
        ToolCallRecord(
            tool_name="read_file",
            input_summary=path,
            output_summary=f"读取 {result.start_line}-{result.end_line} 行。",
            status="success",
        ),
    )


def _dedupe_evidence(evidence: list[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[EvidenceRef] = []
    for item in evidence:
        key = (item.path, item.reason, item.source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _build_tool_calls(
    scan: ProjectScanResult,
    evidence: list[EvidenceRef],
    evidence_tool_calls: list[ToolCallRecord],
) -> list[ToolCallRecord]:
    return [
        ToolCallRecord(
            tool_name="list_files",
            input_summary=scan.project_path,
            output_summary=f"扫描到 {len(scan.file_tree)} 个文件树条目。",
            status="success",
        ),
        ToolCallRecord(
            tool_name="detect_framework",
            input_summary="package/java build metadata + file tree",
            output_summary=f"识别 {len(scan.detected_stack)} 个技术栈标签。",
            status="success",
        ),
        *evidence_tool_calls,
        ToolCallRecord(
            tool_name="project_interpreter",
            input_summary="scan result + selected skill",
            output_summary=f"生成 {len(evidence)} 条证据引用。",
            status="success",
        ),
    ]


def _suggest_questions(scan: ProjectScanResult, skill: str) -> list[str]:
    if skill == SETUP_ANALYSIS_SKILL:
        return ["我应该从哪些文件开始读？", "前端结构是怎么组织的？"]
    if skill == FRONTEND_ANALYSIS_SKILL:
        questions = ["这个项目怎么运行？", "状态管理逻辑在哪里？"]
        if any(path for path in _frontend_candidate_paths(scan) if "router" in path):
            questions.append("路由和页面之间是什么关系？")
        return questions
    return ["这个项目怎么运行？", "前端结构是怎么组织的？", "有哪些登录或 API 候选文件？"]


def _find_flow_candidates(scan: ProjectScanResult) -> tuple[list[EvidenceRef], list[ToolCallRecord]]:
    queries = ("login", "auth", "token", "@GetMapping", "@PostMapping", "axios", "fetch")
    evidence: list[EvidenceRef] = []
    tool_calls: list[ToolCallRecord] = []
    for query in queries:
        try:
            result = search_code(scan.project_path, query, max_matches=5)
        except (ReadOnlyToolError, ValueError) as exc:
            tool_calls.append(
                ToolCallRecord(
                    tool_name="search_code",
                    input_summary=query,
                    output_summary="搜索失败。",
                    status="error",
                    error=str(exc),
                )
            )
            continue
        for match in result.matches[:3]:
            evidence.append(
                EvidenceRef(
                    path=match.path,
                    reason=f"搜索到登录/API 候选关键词：{query}。",
                    source="search_code",
                    start_line=match.line_number,
                    end_line=match.line_number,
                    excerpt=match.line,
                )
            )
        tool_calls.append(
            ToolCallRecord(
                tool_name="search_code",
                input_summary=query,
                output_summary=f"{result.used_backend} 返回 {len(result.matches)} 个候选匹配。",
                status="success",
            )
        )
    return evidence, tool_calls


def _evidence_path_from_source(source: str) -> str:
    if source.startswith("package.json"):
        return "package.json"
    if source.startswith("pom.xml"):
        return "pom.xml"
    if source.startswith("build.gradle"):
        return "build.gradle"
    if source.startswith("file_tree:"):
        return "<file_tree>"
    return source


def _java_build_path(scan: ProjectScanResult) -> str:
    if scan.java_build.build_tool == "maven":
        return "pom.xml"
    if scan.java_build.build_tool == "gradle":
        return "build.gradle"
    return "<file_tree>"


def _format_scan_context(
    scan: ProjectScanResult,
    evidence: list[EvidenceRef],
    reading_path: list[ReadingPathItem],
) -> str:
    stack = ", ".join(tag.name for tag in scan.detected_stack) or "unknown"
    scripts = ", ".join(f"{name}: {command}" for name, command in sorted(scan.package.scripts.items())) or "none"
    java_dependencies = ", ".join(sorted(scan.java_build.dependencies)) or "none"
    entrypoints = ", ".join(entrypoint.path for entrypoint in scan.entrypoints) or "none"
    evidence_paths = ", ".join(item.path for item in evidence) or "none"
    reading_paths = ", ".join(item.path for item in reading_path) or "none"

    return "\n".join(
        [
            f"project_name: {scan.project_name}",
            f"project_path: {scan.project_path}",
            f"package_manager: {scan.package.package_manager or 'unknown'}",
            f"java_build_tool: {scan.java_build.build_tool or 'unknown'}",
            f"java_artifact_id: {scan.java_build.artifact_id or 'unknown'}",
            f"java_dependencies: {java_dependencies}",
            f"detected_stack: {stack}",
            f"scripts: {scripts}",
            f"entrypoints: {entrypoints}",
            f"recommended_reading_path: {reading_paths}",
            f"evidence_paths: {evidence_paths}",
            f"warnings: {'; '.join(scan.warnings) if scan.warnings else 'none'}",
        ]
    )
