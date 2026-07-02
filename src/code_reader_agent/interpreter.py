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
)
from code_reader_agent.prompts import (
    PROJECT_INTERPRETER_PROMPT_VERSION,
    PROJECT_INTERPRETER_SYSTEM_PROMPT,
    build_project_interpreter_user_prompt,
)
from code_reader_agent.scanner import scan_project


PROJECT_OVERVIEW_SKILL = "project_overview_skill"


def interpret_project(project_path: str, question: str | None = None) -> ProjectInterpretationResult:
    """Scan a project and produce a Phase 4 single-agent interpretation."""

    effective_question = question or "这个项目是干什么的？我应该怎么运行，并从哪些文件开始看？"
    scan = scan_project(project_path)
    return interpret_scan(scan, effective_question)


def interpret_scan(scan: ProjectScanResult, question: str) -> ProjectInterpretationResult:
    """Interpret an existing scan result without reading more project files."""

    evidence = _build_evidence(scan)
    reading_path = _build_reading_path(scan.entrypoints)
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

    return ProjectInterpretationResult(
        project_name=scan.project_name,
        question=question,
        skill=PROJECT_OVERVIEW_SKILL,
        prompt_version=PROJECT_INTERPRETER_PROMPT_VERSION,
        prompt_messages=prompt_messages,
        overview=_build_overview(scan),
        setup_summary=_build_setup_summary(scan),
        reading_path=reading_path,
        evidence=evidence,
        warnings=warnings,
    )


def _build_overview(scan: ProjectScanResult) -> str:
    stack_names = [tag.name for tag in scan.detected_stack]
    if not stack_names:
        return f"{scan.project_name} 是一个本地项目；当前扫描未找到足够的技术栈证据。"

    stack_summary = "、".join(stack_names)
    return f"{scan.project_name} 看起来是一个基于 {stack_summary} 的项目。该判断来自 package.json、入口文件和文件树扫描。"


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


def _build_evidence(scan: ProjectScanResult) -> list[EvidenceRef]:
    evidence: list[EvidenceRef] = []
    if scan.package.found:
        evidence.append(EvidenceRef(path="package.json", reason="项目名称、依赖、包管理器和 scripts。", source="read_config"))
    if scan.java_build.found:
        evidence.append(
            EvidenceRef(
                path=_java_build_path(scan),
                reason="Java 构建工具、项目坐标、依赖和配置文件。",
                source="read_config",
            )
        )

    for entrypoint in scan.entrypoints:
        evidence.append(EvidenceRef(path=entrypoint.path, reason=f"检测到 {entrypoint.kind} 入口文件。", source="find_entrypoints"))

    for tag in scan.detected_stack:
        evidence.append(EvidenceRef(path=_evidence_path_from_source(tag.source), reason=f"识别技术栈：{tag.name}。", source="detect_framework"))

    return _dedupe_evidence(evidence)


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
