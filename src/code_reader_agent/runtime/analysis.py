"""Deterministic analysis contract for the CodeReader Agent MVP."""

from __future__ import annotations

from hashlib import sha1

from code_reader_agent.models import (
    AgentRunResult,
    AgentStep,
    AnalysisPlanItem,
    ContextSnapshot,
    EvidenceRef,
    ProjectInterpretationResult,
    ProjectManual,
    ProjectManualDirectory,
    ProjectManualEntrypoint,
    ProjectManualModule,
    ProjectReport,
    ReadingPathItem,
    RepoMap,
    ToolCallRecord,
    TraceEvent,
)
from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import scan_project


def enrich_agent_run_result(
    *,
    project_path: str,
    question: str,
    project_name: str,
    skill: str,
    final_answer: str,
    evidence: list[EvidenceRef],
    tool_calls: list[ToolCallRecord],
    read_files: list[str],
    suggested_questions: list[str],
    warnings: list[str],
    agent_steps: list[AgentStep],
    used_llm: bool,
    fallback_used: bool,
    fallback_result: ProjectInterpretationResult | None,
    project_manual_context: ProjectManual | None = None,
) -> AgentRunResult:
    """Attach plan, skills, context, report, and trace to an agent run."""

    repo_map = build_repo_map(scan_project(project_path))
    selected_skills = select_skills(repo_map)
    analysis_goal = build_analysis_goal(question)
    analysis_plan = build_analysis_plan(question, repo_map, selected_skills)
    project_manual = build_project_manual(repo_map)
    project_memory = build_project_memory(repo_map, project_manual)
    context_snapshot = build_context_snapshot(
        repo_map,
        question,
        selected_skills,
        evidence,
        read_files,
        project_manual_context,
    )
    report = build_project_report(
        repo_map=repo_map,
        question=question,
        final_answer=final_answer,
        evidence=evidence or (fallback_result.evidence if fallback_result else []),
        warnings=warnings,
        fallback_result=fallback_result,
    )
    trace_events = build_trace_events(
        analysis_plan=analysis_plan,
        selected_skills=selected_skills,
        context_snapshot=context_snapshot,
        tool_calls=tool_calls,
        agent_steps=agent_steps,
        report=report,
        used_llm=used_llm,
        fallback_used=fallback_used,
    )

    return AgentRunResult(
        task_id=build_task_id(project_path, question),
        project_name=project_name,
        question=question,
        skill=skill,
        analysis_goal=analysis_goal,
        analysis_plan=analysis_plan,
        selected_skills=selected_skills,
        context_snapshot=context_snapshot,
        project_manual=project_manual,
        project_memory=project_memory,
        report=report,
        trace_events=trace_events,
        final_answer=final_answer,
        evidence=evidence,
        tool_calls=tool_calls,
        read_files=read_files,
        suggested_questions=suggested_questions,
        warnings=warnings,
        agent_steps=agent_steps,
        used_llm=used_llm,
        fallback_used=fallback_used,
        fallback_result=fallback_result,
    )


def build_task_id(project_path: str, question: str) -> str:
    """Build a stable local task id for the non-persistent MVP flow."""

    digest = sha1(f"{project_path}\n{question}".encode("utf-8")).hexdigest()[:12]
    return f"task-{digest}"


def build_analysis_goal(question: str) -> str:
    """Normalize the user request into a codebase understanding goal."""

    stripped = question.strip()
    if stripped:
        return f"围绕用户目标生成可复用的代码库理解报告：{stripped}"
    return "生成项目地图、模块说明、关键入口、阅读路线和证据链。"


def select_skills(repo_map: RepoMap) -> list[str]:
    """Select first-version skills from detected stack tags."""

    stack_names = {tag.name for tag in repo_map.detected_stack}
    skills = ["CodebaseOverviewSkill"]
    if stack_names & {"Spring Boot", "Spring Web", "Spring Security", "Maven", "Gradle", "Java"}:
        skills.append("SpringBootSkill")
    if stack_names & {"Vue", "Vite", "Vue Router", "Pinia"}:
        skills.append("VueSkill")
    if repo_map.api_endpoints or repo_map.api_flows:
        skills.append("ApiFlowCandidateSkill")
    if repo_map.auth_flows:
        skills.append("AuthFlowCandidateSkill")
    return _dedupe_strings(skills)


def build_analysis_plan(question: str, repo_map: RepoMap, selected_skills: list[str]) -> list[AnalysisPlanItem]:
    """Create the fixed MVP plan shown as the Planner output."""

    skill_text = ", ".join(selected_skills)
    return [
        AnalysisPlanItem(
            order=1,
            actor="Planner",
            title="创建分析任务",
            description=build_analysis_goal(question),
            expected_output="明确本次分析目标和完成条件。",
        ),
        AnalysisPlanItem(
            order=2,
            actor="Tool Executor",
            title="扫描项目与构建 Repo Map",
            description=f"读取 {repo_map.project_name} 的文件树、配置、入口和模块线索。",
            tool="scan_project, build_repo_map",
            expected_output="项目地图、技术栈、入口文件、模块和 evidence。",
        ),
        AnalysisPlanItem(
            order=3,
            actor="Context Manager",
            title="组织上下文",
            description="按任务选择项目上下文、任务上下文、符号上下文和当前记忆上下文。",
            expected_output="可展示、可追踪的上下文快照。",
        ),
        AnalysisPlanItem(
            order=4,
            actor="Skill Registry",
            title="选择技术栈 Skill",
            description=f"根据检测到的技术栈选择 {skill_text}。",
            expected_output="本次分析使用的 skill 列表。",
        ),
        AnalysisPlanItem(
            order=5,
            actor="Analyzer",
            title="生成理解结果",
            description="基于工具结果和上下文分析模块、入口、阅读路线和候选调用链。",
            expected_output="结构化 findings 和不确定点。",
        ),
        AnalysisPlanItem(
            order=6,
            actor="Report Writer",
            title="输出项目解读报告",
            description="生成可复用的项目地图、模块说明、关键入口、阅读路线和证据报告。",
            expected_output="结构化项目解读文档和 trace events。",
        ),
    ]


def build_context_snapshot(
    repo_map: RepoMap,
    question: str,
    selected_skills: list[str],
    evidence: list[EvidenceRef],
    read_files: list[str],
    project_manual_context: ProjectManual | None = None,
) -> ContextSnapshot:
    """Build the MVP context manager output."""

    stack = ", ".join(tag.name for tag in repo_map.detected_stack[:8]) or "未识别明确技术栈"
    modules = ", ".join(module.name for module in repo_map.modules[:8]) or "暂无模块"
    entrypoints = ", ".join(entry.path for entry in repo_map.entrypoints[:8]) or "暂无入口"
    memory_context = [
        "MVP memory context is limited to the current analysis task.",
        "Persistent cross-task memory is planned but not implemented.",
    ]
    if project_manual_context:
        manual_modules = ", ".join(module.name for module in project_manual_context.modules[:6]) or "暂无模块"
        memory_context.append(f"project_manual_context={project_manual_context.title or repo_map.project_name}")
        memory_context.append(f"manual_modules={manual_modules}")
    return ContextSnapshot(
        project_context=[
            f"project={repo_map.project_name}",
            f"stack={stack}",
            f"package_manager={repo_map.package_manager or 'unknown'}",
            f"java_build_tool={repo_map.java_build_tool or 'unknown'}",
        ],
        task_context=[
            f"goal={build_analysis_goal(question)}",
            f"skills={', '.join(selected_skills)}",
        ],
        symbol_context=[
            f"modules={modules}",
            f"entrypoints={entrypoints}",
        ],
        memory_context=memory_context,
        evidence_count=len(evidence) or len(repo_map.evidence),
        read_files=read_files,
    )


def build_project_manual(repo_map: RepoMap) -> ProjectManual:
    """Build the stable first-pass project manual from deterministic Repo Map data."""

    directory_depth = {entry.path: entry.depth for entry in repo_map.file_tree if entry.kind == "directory"}
    evidence = [
        EvidenceRef(
            path=item.path,
            reason=item.reason,
            source=item.collected_by_tool,
            start_line=item.start_line,
            end_line=item.end_line,
            excerpt=item.excerpt,
        )
        for item in repo_map.evidence[:12]
    ]
    uncertainties = _dedupe_strings(
        [
            *repo_map.warnings,
            "项目说明书基于只读扫描、Repo Map 和 evidence 生成，不代表运行时行为已验证。",
            "调用链仍为候选级结果，后续追问可继续通过 read_file/search_code 补充上下文。",
        ]
    )
    return ProjectManual(
        title=f"{repo_map.project_name} 项目说明书",
        overview=repo_map.project_summary,
        technology_stack=repo_map.stack_explanations[:12],
        modules=[
            ProjectManualModule(
                id=module.id,
                name=module.name,
                type=module.type,
                responsibility=module.responsibility,
                key_files=module.key_files,
                entry_files=module.entry_files,
                confidence=module.confidence,
            )
            for module in sorted(repo_map.modules, key=lambda item: (item.reading_priority, item.name))[:12]
        ],
        entrypoints=[
            ProjectManualEntrypoint(
                path=entrypoint.path,
                kind=entrypoint.kind,
                reason=_entrypoint_reason(entrypoint.kind),
            )
            for entrypoint in repo_map.entrypoints[:12]
        ],
        directory_tree=repo_map.file_tree[:120],
        key_directories=[
            ProjectManualDirectory(
                path=directory.path,
                depth=directory_depth.get(directory.path, 0),
                role=directory.role,
                importance=directory.importance,
                reason=directory.reason,
            )
            for directory in repo_map.directory_insights[:18]
        ],
        evidence=evidence,
        uncertainties=uncertainties,
    )


def build_project_report(
    *,
    repo_map: RepoMap,
    question: str,
    final_answer: str,
    evidence: list[EvidenceRef],
    warnings: list[str],
    fallback_result: ProjectInterpretationResult | None = None,
) -> ProjectReport:
    """Create a structured report from repo map and agent output."""

    summary = repo_map.project_summary.one_liner if repo_map.project_summary else final_answer.splitlines()[0]
    module_summaries = [
        f"{module.name}: {module.responsibility}"
        for module in sorted(repo_map.modules, key=lambda item: (item.reading_priority, item.name))[:8]
    ]
    key_entrypoints = [entry.path for entry in repo_map.entrypoints[:10]]
    reading_route = _reading_route(repo_map, fallback_result)
    call_chain_candidates = _call_chain_candidates(repo_map)
    uncertainties = _dedupe_strings(
        [
            *warnings,
            *repo_map.warnings,
            "调用链为候选级结果，MVP 尚未实现精准 AST 级跨文件追踪。",
        ]
    )
    return ProjectReport(
        title=f"{repo_map.project_name} 项目解读报告",
        project_map=(
            f"{summary}\n"
            f"分析目标：{question}\n"
            f"当前报告基于 Repo Map、只读工具调用和 evidence 生成。"
        ),
        module_summaries=module_summaries,
        key_entrypoints=key_entrypoints,
        reading_route=reading_route,
        call_chain_candidates=call_chain_candidates,
        evidence=evidence[:12],
        uncertainties=uncertainties,
    )


def build_trace_events(
    *,
    analysis_plan: list[AnalysisPlanItem],
    selected_skills: list[str],
    context_snapshot: ContextSnapshot,
    tool_calls: list[ToolCallRecord],
    agent_steps: list[AgentStep],
    report: ProjectReport,
    used_llm: bool,
    fallback_used: bool,
) -> list[TraceEvent]:
    """Create UI-visible trace events for the local non-persistent task."""

    events: list[TraceEvent] = []
    for item in analysis_plan:
        events.append(
            TraceEvent(
                index=len(events) + 1,
                stage=item.actor,
                title=item.title,
                summary=item.description,
                status="success",
                tool_name=item.tool,
            )
        )
    events.append(
        TraceEvent(
            index=len(events) + 1,
            stage="Skill Registry",
            title="Skill selection",
            summary=", ".join(selected_skills),
        )
    )
    events.append(
        TraceEvent(
            index=len(events) + 1,
            stage="Context Manager",
            title="Context snapshot",
            summary=f"{context_snapshot.evidence_count} evidence items, {len(context_snapshot.read_files)} read files.",
        )
    )
    for call in tool_calls:
        events.append(
            TraceEvent(
                index=len(events) + 1,
                stage="Tool Executor",
                title=call.tool_name,
                summary=call.output_summary,
                status=call.status,
                tool_name=call.tool_name,
            )
        )
    for step in agent_steps:
        events.append(
            TraceEvent(
                index=len(events) + 1,
                stage="Agent Runtime",
                title=step.title,
                summary=step.summary,
                status=step.status,
                tool_name=step.tool_name,
            )
        )
    mode = "LLM Agent" if used_llm else "Deterministic fallback"
    if fallback_used:
        mode = "Deterministic fallback"
    events.append(
        TraceEvent(
            index=len(events) + 1,
            stage="Report Writer",
            title=report.title,
            summary=f"{mode} produced a structured report with {len(report.module_summaries)} module summaries.",
        )
    )
    return events


def _reading_route(repo_map: RepoMap, fallback_result: ProjectInterpretationResult | None) -> list[ReadingPathItem]:
    if fallback_result and fallback_result.reading_path:
        return fallback_result.reading_path
    read_first = [
        item
        for item in sorted(repo_map.reading_recommendations, key=lambda row: row.priority)
        if item.action == "read_first"
    ]
    return [
        ReadingPathItem(order=index, path=item.path, reason=item.reason)
        for index, item in enumerate(read_first[:8], start=1)
    ]


def _call_chain_candidates(repo_map: RepoMap) -> list[str]:
    candidates: list[str] = []
    candidates.extend(f"API endpoint candidate: {path}" for path in repo_map.api_endpoints[:8])
    candidates.extend(f"Auth flow candidate: {path}" for path in repo_map.auth_flows[:8])
    candidates.extend(f"Controller -> Service -> Repository candidate: {path}" for path in repo_map.controllers[:5])
    if not candidates:
        candidates.append("未找到明确调用链候选；需要后续通过 search_code/read_file 继续收集证据。")
    return candidates


def _entrypoint_reason(kind: str) -> str:
    return {
        "app_entry": "前端应用入口，用于确认应用如何挂载和启动。",
        "root_component": "前端根组件入口，用于理解页面外壳和全局布局。",
        "router": "前端路由入口，用于理解页面导航结构。",
        "vite_config": "Vite 构建配置入口，用于确认开发和构建方式。",
        "java_app_entry": "Java/Spring Boot 应用入口，用于确认后端服务启动类。",
        "java_controller": "Java HTTP Controller 入口候选，用于从外部请求开始阅读。",
        "java_service": "Java Service 入口候选，用于继续理解业务逻辑边界。",
        "java_repository": "Java Repository 入口候选，用于理解数据访问边界。",
        "java_mapper": "Java Mapper 入口候选，用于理解数据访问或 SQL 映射边界。",
        "java_config": "Java 配置入口，用于确认运行配置和依赖约定。",
    }.get(kind, "扫描器识别出的项目入口候选，需要按需继续读取确认。")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
