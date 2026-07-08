"""LangGraph Ask mode workflow for report-side project questions."""

from __future__ import annotations

import re
from typing import Any, NotRequired, TypedDict

try:
    from langgraph.graph import END, StateGraph
except ModuleNotFoundError:  # pragma: no cover - exercised only when dependency installation is blocked.
    END = "__end__"

    class StateGraph:  # type: ignore[no-redef]
        """Small sequential fallback used only when langgraph is not installed."""

        def __init__(self, _schema: object) -> None:
            self._nodes: dict[str, Any] = {}
            self._edges: dict[str, str] = {}
            self._entry = ""

        def add_node(self, name: str, node: Any) -> None:
            self._nodes[name] = node

        def add_edge(self, start: str, end: str) -> None:
            self._edges[start] = end

        def set_entry_point(self, name: str) -> None:
            self._entry = name

        def compile(self) -> Any:
            graph = self

            class _CompiledGraph:
                def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                    current = graph._entry
                    next_state = dict(state)
                    while current and current != END:
                        next_state = graph._nodes[current](next_state)
                        current = graph._edges.get(current, END)
                    return next_state

            return _CompiledGraph()

from code_reader_agent.local_state import (
    get_project_memory,
    get_session_memory,
    project_id_for_path,
    save_project_memory,
    save_session_memory,
)
from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.models import (
    ApiIndexEntry,
    AskIntent,
    AskModeResult,
    CodeEvidence,
    ContextPack,
    EvidenceRef,
    FileMemorySummary,
    FlowIndexEntry,
    IntentResult,
    ModuleMemorySummary,
    PlannedToolCall,
    ProjectMemory,
    QueryHint,
    ResolvedQuery,
    RoutedSkillInfo,
    SessionMemory,
    SessionMemoryTurn,
    SymbolIndexItem,
    ToolCallRecord,
    ToolPlan,
    TraceEvent,
)
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import scan_project
from code_reader_agent.skills.registry import KNOWLEDGE_INDEX_VERSION, default_skill_registry
from code_reader_agent.tools.read_only import (
    ReadOnlyToolError,
    list_files,
    parse_api_calls,
    parse_controller,
    parse_dependencies,
    parse_mapper,
    parse_routes,
    read_file,
    search_api_path,
    search_keyword,
    search_symbol,
)


CONTEXT_PACK_CHAR_BUDGET = 12_000
MAX_TOOL_CALLS = 8
FOLLOWUP_MARKERS = ("这个", "那个", "那", "它", "这里", "那里", "上面", "刚才", "继续", "this", "that", "it")
IMPLEMENTATION_MARKERS = (
    "实现",
    "调用",
    "哪里",
    "在哪",
    "方法",
    "函数",
    "类",
    "字段",
    "token",
    "权限",
    "校验",
    "数据从哪里",
    "where",
    "called",
    "implemented",
)
LEGACY_INTENTS: dict[str, AskIntent] = {
    "api_usage": "api_lookup",
    "call_chain": "flow_trace",
    "configuration": "config_lookup",
}


class AskState(TypedDict):
    project_path: str
    question: str
    project_memory: ProjectMemory
    session_memory: SessionMemory
    resolved_query: NotRequired[ResolvedQuery]
    intent: NotRequired[AskIntent]
    intent_result: NotRequired[IntentResult]
    retrieved_context: NotRequired[list[str]]
    relevant_modules: NotRequired[list[ModuleMemorySummary]]
    relevant_files: NotRequired[list[FileMemorySummary]]
    relevant_apis: NotRequired[list[ApiIndexEntry]]
    relevant_flows: NotRequired[list[FlowIndexEntry]]
    query_hints: NotRequired[list[QueryHint]]
    routed_skills: NotRequired[list[RoutedSkillInfo]]
    related_files: NotRequired[list[str]]
    related_apis: NotRequired[list[str]]
    related_flows: NotRequired[list[str]]
    implementation_path: NotRequired[list[str]]
    tool_plan: NotRequired[ToolPlan]
    references: NotRequired[list[EvidenceRef]]
    tool_calls: NotRequired[list[ToolCallRecord]]
    code_evidence: NotRequired[list[CodeEvidence]]
    context_pack: NotRequired[ContextPack]
    skill_answer_prompts: NotRequired[list[str]]
    key_code_notes: NotRequired[list[str]]
    answer: NotRequired[str]
    warnings: NotRequired[list[str]]
    trace_events: NotRequired[list[TraceEvent]]


def run_ask_mode(
    project_path: str,
    question: str,
    session_memory: SessionMemory | None = None,
) -> AskModeResult:
    """Run the structured Ask workflow for a project question."""

    repo_map = build_repo_map(scan_project(project_path))
    project_memory = get_project_memory(project_path)
    if project_memory is None or project_memory.knowledge_index_version != KNOWLEDGE_INDEX_VERSION:
        project_memory = save_project_memory(build_project_memory(repo_map))
    active_session_memory = session_memory or get_session_memory(project_path) or SessionMemory(project_id=project_id_for_path(project_path))

    graph = _build_graph()
    state = graph.invoke(
        {
            "project_path": project_path,
            "question": question,
            "project_memory": project_memory,
            "session_memory": active_session_memory,
            "retrieved_context": [],
            "relevant_modules": [],
            "relevant_files": [],
            "relevant_apis": [],
            "relevant_flows": [],
            "query_hints": [],
            "routed_skills": [],
            "related_files": [],
            "related_apis": [],
            "related_flows": [],
            "implementation_path": [],
            "references": [],
            "tool_calls": [],
            "code_evidence": [],
            "skill_answer_prompts": [],
            "key_code_notes": [],
            "warnings": [],
            "trace_events": [],
        }
    )
    return AskModeResult(
        project_id=project_memory.project_id,
        project_name=project_memory.project_name,
        question=question,
        intent=state["intent"],
        answer=state.get("answer", ""),
        resolved_query=state.get("resolved_query"),
        intent_result=state.get("intent_result"),
        tool_plan=state.get("tool_plan"),
        context_pack=state.get("context_pack"),
        routed_skills=state.get("routed_skills", []),
        query_hints=state.get("query_hints", []),
        code_evidence=_dedupe_code_evidence(state.get("code_evidence", [])),
        related_files=_dedupe_strings(state.get("related_files", [])),
        implementation_path=_dedupe_strings(state.get("implementation_path", [])),
        key_code_notes=_dedupe_strings(state.get("key_code_notes", [])),
        references=_dedupe_evidence(state.get("references", [])),
        tool_calls=state.get("tool_calls", []),
        trace_events=state.get("trace_events", []),
        session_memory=state.get("session_memory", active_session_memory),
        warnings=_dedupe_strings(state.get("warnings", [])),
    )


def classify_ask_intent(question: str, project_memory: ProjectMemory, session_memory: SessionMemory | None = None) -> AskIntent:
    """Classify Ask mode question intent with deterministic rules."""

    return _classify_intent_result(
        ResolvedQuery(
            original_question=question,
            resolved_question=question,
            referenced_files=_session_files(session_memory),
            referenced_apis=_session_apis(session_memory),
            referenced_flows=_session_flows(session_memory),
        ),
        project_memory,
        session_memory,
    ).intent


def normalize_ask_intent(intent: str) -> AskIntent:
    """Normalize legacy intent values to the current public names."""

    return LEGACY_INTENTS.get(intent, intent)  # type: ignore[return-value]


def _build_graph() -> Any:
    graph = StateGraph(AskState)
    graph.add_node("QueryRewriter", _query_rewriter)
    graph.add_node("IntentClassifier", _intent_classifier)
    graph.add_node("SkillRouter", _skill_router)
    graph.add_node("ContextRetriever", _context_retriever)
    graph.add_node("ToolPlanner", _tool_planner)
    graph.add_node("EvidenceCollector", _evidence_collector)
    graph.add_node("ContextBuilder", _context_builder)
    graph.add_node("AnswerComposer", _answer_composer)
    graph.add_node("MemoryUpdater", _memory_updater)
    graph.set_entry_point("QueryRewriter")
    graph.add_edge("QueryRewriter", "IntentClassifier")
    graph.add_edge("IntentClassifier", "SkillRouter")
    graph.add_edge("SkillRouter", "ContextRetriever")
    graph.add_edge("ContextRetriever", "ToolPlanner")
    graph.add_edge("ToolPlanner", "EvidenceCollector")
    graph.add_edge("EvidenceCollector", "ContextBuilder")
    graph.add_edge("ContextBuilder", "AnswerComposer")
    graph.add_edge("AnswerComposer", "MemoryUpdater")
    graph.add_edge("MemoryUpdater", END)
    return graph.compile()


def _query_rewriter(state: AskState) -> AskState:
    question = state["question"].strip()
    session_memory = state["session_memory"]
    referenced_files = _session_files(session_memory)
    referenced_apis = _session_apis(session_memory)
    referenced_flows = _session_flows(session_memory)
    referenced_topic = session_memory.current_topic or _last_answer_topic(session_memory)

    resolved_question = question
    if _is_followup(question) and (referenced_topic or referenced_files or referenced_apis or referenced_flows):
        parts = ["用户正在延续上一轮上下文"]
        if referenced_topic:
            parts.append(f"话题={referenced_topic}")
        if referenced_apis:
            parts.append(f"接口={', '.join(referenced_apis[:4])}")
        if referenced_files:
            parts.append(f"文件={', '.join(referenced_files[:5])}")
        if referenced_flows:
            parts.append(f"流程={', '.join(referenced_flows[:3])}")
        resolved_question = f"{'；'.join(parts)}。当前问题：{question}"

    resolved = ResolvedQuery(
        original_question=question,
        resolved_question=resolved_question,
        referenced_topic=referenced_topic,
        referenced_files=referenced_files,
        referenced_apis=referenced_apis,
        referenced_flows=referenced_flows,
    )
    return {
        **state,
        "resolved_query": resolved,
        "trace_events": _append_trace(state, "Query Rewriter", "指代消解", f"Resolved question: {resolved.resolved_question[:180]}"),
    }


def _intent_classifier(state: AskState) -> AskState:
    intent_result = _classify_intent_result(state["resolved_query"], state["project_memory"], state.get("session_memory"))
    return {
        **state,
        "intent": intent_result.intent,
        "intent_result": intent_result,
        "trace_events": _append_trace(state, "Intent Classifier", intent_result.intent, f"Question classified as {intent_result.intent}."),
    }


def _skill_router(state: AskState) -> AskState:
    routed_skills = default_skill_registry().route_query_skills(
        state["resolved_query"],
        state["intent_result"],
        state["project_memory"],
        state["session_memory"],
    )
    names = ", ".join(skill.name for skill in routed_skills) or "none"
    return {
        **state,
        "routed_skills": routed_skills,
        "trace_events": _append_trace(state, "Skill Router", "问题级 Skill 路由", f"Routed skills for this Ask turn: {names}."),
    }


def _classify_intent_result(resolved_query: ResolvedQuery, project_memory: ProjectMemory, session_memory: SessionMemory | None) -> IntentResult:
    question = resolved_query.resolved_question
    lowered = question.lower()
    original_lowered = resolved_query.original_question.lower()
    keywords = _extract_keywords(question)
    possible_files = _matched_file_paths(project_memory, question)
    possible_apis = [entry.path for entry in _matched_api_entries(project_memory, question)]
    possible_symbols = [item.name for item in _matched_symbols(project_memory, question)]

    if any(keyword in lowered for keyword in ("技术栈", "框架", "framework", "dependencies", "依赖")):
        intent: AskIntent = "tech_stack"
    elif any(keyword in original_lowered for keyword in ("接口", "api", "endpoint", "调用", "where is this called")):
        intent = "api_lookup"
    elif any(keyword in lowered for keyword in ("配置", "数据库", "application.yml", "application.properties", ".env", "pom.xml", "package.json", "vite.config")):
        intent = "config_lookup"
    elif session_memory and _is_followup(resolved_query.original_question) and session_memory.turns and not any(
        keyword in original_lowered for keyword in ("接口", "api", "endpoint", "调用", "where")
    ):
        intent = normalize_ask_intent(session_memory.turns[-1].intent)
    elif possible_apis:
        intent = "api_lookup"
    elif any(keyword in lowered for keyword in ("调用链", "流程", "怎么走", "数据从哪里", "登录流程", "认证流程", "auth flow", "flow")):
        intent = "flow_trace"
    elif possible_files or any(keyword in question for keyword in ("文件", "Controller", "Service", ".vue", ".ts", ".java", ".xml")):
        intent = "file_explanation"
    elif possible_symbols or any(keyword in lowered for keyword in ("符号", "方法", "函数", "类", "字段", "symbol", "method", "function", "class")):
        intent = "symbol_lookup"
    elif any(keyword in lowered for keyword in ("模块", "权限", "登录", "认证", "module", "实现")):
        intent = "module_explanation"
    elif session_memory and _is_followup(resolved_query.original_question) and session_memory.turns:
        intent = normalize_ask_intent(session_memory.turns[-1].intent)
    elif any(keyword in lowered for keyword in ("做什么", "是什么", "总览", "介绍", "overview")):
        intent = "project_overview"
    else:
        intent = "unknown"

    need_code_evidence = intent in {"file_explanation", "api_lookup", "flow_trace", "config_lookup", "symbol_lookup"} or any(
        marker in lowered for marker in IMPLEMENTATION_MARKERS
    )
    if intent in {"project_overview", "tech_stack"} and not any(marker in lowered for marker in IMPLEMENTATION_MARKERS):
        need_code_evidence = False

    return IntentResult(
        intent=intent,
        keywords=keywords,
        possible_files=possible_files[:8],
        possible_apis=possible_apis[:8],
        possible_symbols=possible_symbols[:8],
        need_code_evidence=need_code_evidence,
    )


def _context_retriever(state: AskState) -> AskState:
    memory = state["project_memory"]
    resolved = state["resolved_query"]
    intent_result = state["intent_result"]
    question = resolved.resolved_question
    routed_skills = state.get("routed_skills", [])
    query_hints = default_skill_registry().collect_query_hints(resolved, state["session_memory"], routed_skills)
    hinted_question = _question_with_hints(question, query_hints)

    modules = _rank_modules(memory, hinted_question, resolved)
    files = _rank_files(memory, hinted_question, resolved, intent_result)
    apis = _rank_apis(memory, hinted_question, resolved)
    flows = _rank_flows(memory, hinted_question, resolved)

    if intent_result.intent == "project_overview":
        files = memory.file_summaries[:6]
        modules = memory.module_summaries[:4]
    elif intent_result.intent == "tech_stack":
        files = _files_by_paths(memory, memory.project_memory.config_files)[:8]
    elif intent_result.intent == "config_lookup":
        files = _files_by_paths(memory, memory.project_memory.config_files) or files
    elif intent_result.intent == "module_explanation" and not modules:
        modules = memory.module_summaries[:3]
    elif intent_result.intent == "api_lookup" and not apis:
        apis = memory.api_index[:5]
    elif intent_result.intent == "flow_trace" and not flows:
        flows = memory.flow_index[:4]
    elif intent_result.intent == "symbol_lookup" and not files:
        symbol_files = [item.file_path for item in _matched_symbols(memory, question)]
        files = _files_by_paths(memory, symbol_files)

    related_files = _dedupe_strings(
        [
            *[item.path for item in files],
            *[path for module in modules for path in module.related_files],
            *[entry.backend_file for entry in apis if entry.backend_file],
            *[path for entry in apis for path in entry.frontend_calls],
            *[path for flow in flows for path in flow.evidence_files],
            *resolved.referenced_files,
        ]
    )
    related_apis = _dedupe_strings([*[entry.path for entry in apis], *resolved.referenced_apis])
    related_flows = _dedupe_strings([*[flow.name for flow in flows], *resolved.referenced_flows])
    implementation_path = _dedupe_strings(
        [
            *[path for entry in apis for path in entry.frontend_calls],
            *[entry.backend_file for entry in apis if entry.backend_file],
            *[path for flow in flows for path in flow.steps],
            *related_files,
        ]
    )
    context = _dedupe_strings(
        [
            memory.project_memory.positioning,
            *[f"module:{item.name} {item.responsibility}" for item in modules],
            *[f"file:{item.path} {item.role} {item.responsibility}" for item in files],
            *[_api_context(item) for item in apis],
            *[f"flow:{item.name} {' -> '.join(item.steps)}" for item in flows],
        ]
    )

    return {
        **state,
        "retrieved_context": context,
        "relevant_modules": modules[:6],
        "relevant_files": files[:10],
        "relevant_apis": apis[:8],
        "relevant_flows": flows[:6],
        "query_hints": query_hints,
        "related_files": related_files[:20],
        "related_apis": related_apis[:12],
        "related_flows": related_flows[:8],
        "implementation_path": implementation_path[:24],
        "trace_events": _append_trace(
            state,
            "Context Retriever",
            "混合检索",
            f"Retrieved {len(context)} context items, {len(related_files)} files, {len(related_apis)} APIs, {len(query_hints)} skill hints from {len(routed_skills)} routed skills.",
        ),
    }


def _tool_planner(state: AskState) -> AskState:
    intent_result = state["intent_result"]
    resolved = state["resolved_query"]
    question = resolved.resolved_question
    related_files = state.get("related_files", [])
    related_apis = state.get("related_apis", [])
    planned: list[PlannedToolCall] = []

    def add(tool_name: str, args: dict[str, object], purpose: str) -> None:
        if len(planned) >= MAX_TOOL_CALLS:
            return
        key = (tool_name, tuple(sorted(args.items())))
        if any((item.tool_name, tuple(sorted(item.args.items()))) == key for item in planned):
            return
        planned.append(PlannedToolCall(tool_name=tool_name, args=args, purpose=purpose))

    for skill_plan in default_skill_registry().collect_tool_plans(resolved, state.get("retrieved_context", []), state.get("routed_skills", [])):
        add(skill_plan.tool_name, skill_plan.args, skill_plan.purpose)

    if intent_result.intent == "project_overview":
        if not state.get("retrieved_context"):
            add("list_files", {"max_depth": 2}, "项目记忆不足，补充目录结构。")
    elif intent_result.intent == "tech_stack":
        add("parse_dependencies", {}, "确认依赖文件和技术栈证据。")
    elif intent_result.intent == "config_lookup":
        add("parse_dependencies", {}, "读取配置和依赖摘要。")
        for path in related_files[:4]:
            add("read_file", {"relative_path": path, "start_line": 1, "end_line": 80}, "配置类问题需要读取真实配置片段。")
    elif intent_result.intent == "file_explanation":
        for path in related_files[:4]:
            add("read_file", {"relative_path": path, "start_line": 1, "end_line": 140}, "用户询问指定文件，需要读取真实代码片段。")
        if not related_files:
            add("search_symbol", {"symbol": _search_query(question)}, "文件记忆无法定位，按符号继续搜索。")
    elif intent_result.intent == "module_explanation":
        for path in related_files[:4]:
            add("read_file", {"relative_path": path, "start_line": 1, "end_line": 120}, "模块解释涉及实现细节，读取关键文件补充证据。")
        add("search_keyword", {"keyword": _search_query(question)}, "搜索模块相关关键词补足上下文。")
    elif intent_result.intent == "api_lookup":
        add("parse_api_calls", {}, "提取前端 axios/fetch/request 调用候选。")
        add("parse_controller", {}, "提取 Spring Controller 接口候选。")
        for api in related_apis[:3]:
            add("search_api_path", {"api_path": api}, "接口定位需要搜索真实代码中的接口路径。")
    elif intent_result.intent == "flow_trace":
        for path in related_files[:5]:
            add("read_file", {"relative_path": path, "start_line": 1, "end_line": 120}, "流程追踪需要读取关键文件作为链路依据。")
        add("search_keyword", {"keyword": _search_query(question)}, "搜索流程关键词补充链路候选。")
    elif intent_result.intent == "symbol_lookup":
        symbol = intent_result.possible_symbols[0] if intent_result.possible_symbols else _search_query(question)
        add("search_symbol", {"symbol": symbol}, "符号定位需要搜索真实源码。")
        for path in related_files[:3]:
            add("read_file", {"relative_path": path, "start_line": 1, "end_line": 120}, "读取符号所在文件片段。")
    elif intent_result.need_code_evidence:
        add("search_keyword", {"keyword": _search_query(question)}, "问题涉及具体实现，需要搜索真实代码。")

    reason = "问题涉及具体实现或命中 Skill 建议，需要只读工具补充代码证据。" if planned else "项目记忆和索引足以回答该问题。"
    plan = ToolPlan(need_tools=bool(planned), reason=reason, tool_calls=planned)
    return {
        **state,
        "tool_plan": plan,
        "trace_events": _append_trace(state, "Tool Planner", "只读工具计划", f"Planned {len(planned)} tool calls."),
    }


def _evidence_collector(state: AskState) -> AskState:
    references = list(state.get("references", []))
    tool_calls = list(state.get("tool_calls", []))
    related_files = list(state.get("related_files", []))
    implementation_path = list(state.get("implementation_path", []))
    warnings = list(state.get("warnings", []))
    code_evidence = list(state.get("code_evidence", []))
    notes = list(state.get("key_code_notes", []))

    for planned in state.get("tool_plan", ToolPlan(need_tools=False, reason="")).tool_calls:
        result = _execute_ask_tool(state["project_path"], planned)
        tool_calls.append(result["tool_call"])
        references.extend(result.get("references", []))
        related_files.extend(result.get("related_files", []))
        implementation_path.extend(result.get("implementation_path", []))
        warnings.extend(result.get("warnings", []))
        code_evidence.extend(result.get("code_evidence", []))
        notes.extend(result.get("notes", []))

    return {
        **state,
        "references": _dedupe_evidence(references),
        "tool_calls": tool_calls,
        "related_files": _dedupe_strings(related_files),
        "implementation_path": _dedupe_strings(implementation_path),
        "warnings": _dedupe_strings(warnings),
        "code_evidence": _dedupe_code_evidence(code_evidence),
        "key_code_notes": _dedupe_strings(notes),
        "trace_events": _append_trace(state, "Evidence Collector", "工具执行", f"Executed {len(state.get('tool_plan', ToolPlan(need_tools=False, reason='')).tool_calls)} read-only tool calls."),
    }


def _context_builder(state: AskState) -> AskState:
    memory = state["project_memory"]
    resolved = state["resolved_query"]
    memory_evidence = _memory_evidence(state)
    evidence = _dedupe_code_evidence([*state.get("code_evidence", []), *memory_evidence])
    skill_answer_prompts = default_skill_registry().collect_answer_prompts(state.get("routed_skills", []))
    answer_instructions = (
        "先直接回答用户问题；列出相关文件路径；涉及流程时给出候选调用链；"
        "涉及具体实现时引用代码证据；没有明确证据时说明当前代码中未找到明确证据。"
    )
    if skill_answer_prompts:
        answer_instructions = f"{answer_instructions} Skill 回答提示：{' '.join(skill_answer_prompts)}"
    pack = ContextPack(
        user_question=state["question"],
        resolved_question=resolved.resolved_question,
        project_context=_project_context(memory),
        session_context=_session_context(state["session_memory"]),
        relevant_modules=state.get("relevant_modules", []),
        relevant_files=state.get("relevant_files", []),
        relevant_apis=state.get("relevant_apis", []),
        relevant_flows=state.get("relevant_flows", []),
        code_evidence=evidence,
        answer_instructions=answer_instructions,
    )
    pack = _apply_context_budget(pack)
    warnings = list(state.get("warnings", []))
    if pack.truncated:
        warnings.append("Context Pack exceeded budget and was trimmed.")
    return {
        **state,
        "context_pack": pack,
        "code_evidence": pack.code_evidence,
        "skill_answer_prompts": skill_answer_prompts,
        "warnings": _dedupe_strings(warnings),
        "trace_events": _append_trace(state, "Context Builder", "Context Pack", f"Built Context Pack with {len(pack.code_evidence)} evidence items."),
    }


def _answer_composer(state: AskState) -> AskState:
    pack = state["context_pack"]
    answer = _compose_answer(state["intent"], pack, state["project_memory"])
    notes = list(state.get("key_code_notes", []))
    if pack.code_evidence:
        notes.extend(_notes_from_code_evidence(pack.code_evidence))
    else:
        notes.append("当前代码中未找到明确证据。")
    return {
        **state,
        "answer": answer,
        "key_code_notes": _dedupe_strings(notes),
        "trace_events": _append_trace(state, "Answer Composer", "证据化回答", "Composed answer with files, path, and evidence."),
    }


def _memory_updater(state: AskState) -> AskState:
    session_memory = state["session_memory"]
    answer_summary = str(state.get("answer") or "")[:240]
    focused_module = state["context_pack"].relevant_modules[0].name if state["context_pack"].relevant_modules else session_memory.focused_module
    focused_files = _dedupe_strings(state.get("related_files", []))[:12]
    focused_apis = _dedupe_strings(state.get("related_apis", []))[:12]
    focused_flows = _dedupe_strings(state.get("related_flows", []))[:8]
    current_topic = focused_apis[0] if focused_apis else focused_flows[0] if focused_flows else focused_module
    turn = SessionMemoryTurn(
        question=state["question"],
        intent=state["intent"],
        referenced_files=focused_files,
        referenced_apis=focused_apis,
        referenced_flows=focused_flows,
        resolved_question=state["resolved_query"].resolved_question,
        answer_summary=answer_summary,
    )
    updated = session_memory.model_copy(
        update={
            "current_topic": current_topic,
            "focused_module": focused_module,
            "focused_files": focused_files,
            "focused_apis": focused_apis,
            "focused_flows": focused_flows,
            "last_question": state["question"],
            "last_resolved_question": state["resolved_query"].resolved_question,
            "last_answer_summary": answer_summary,
            "turns": [*session_memory.turns[-8:], turn],
        }
    )
    updated = save_session_memory(updated)
    return {
        **state,
        "session_memory": updated,
        "trace_events": _append_trace(state, "Memory Updater", "Session Memory", f"Stored {len(updated.turns)} Ask turns."),
    }


def _execute_ask_tool(project_path: str, planned: PlannedToolCall) -> dict[str, Any]:
    tool_name = planned.tool_name
    args = planned.args
    reason = planned.purpose
    try:
        if tool_name == "list_files":
            entries = list_files(project_path, max_depth=args.get("max_depth") if isinstance(args.get("max_depth"), int) else None)
            return _tool_success(tool_name, "file tree", f"Listed {len(entries)} entries.", reason, notes=[f"文件树包含 {len(entries)} 个条目。"])
        if tool_name == "read_file":
            line_range = _line_range(args)
            result = read_file(project_path, str(args.get("relative_path") or ""), line_range=line_range)
            evidence = EvidenceRef(
                path=result.path,
                reason=reason,
                source="read_file",
                start_line=result.start_line,
                end_line=result.end_line,
                excerpt=_trim_snippet(result.content, 2_000),
            )
            code_evidence = CodeEvidence(
                source="tool",
                file_path=result.path,
                content_summary=f"Read lines {result.start_line}-{result.end_line}.",
                code_snippet=evidence.excerpt,
                relevance_reason=reason,
            )
            return _tool_success(
                tool_name,
                result.path,
                f"Read lines {result.start_line}-{result.end_line}.",
                reason,
                references=[evidence],
                related_files=[result.path],
                warnings=result.warnings,
                code_evidence=[code_evidence],
            )
        if tool_name == "search_keyword":
            keyword = str(args.get("keyword") or args.get("query") or "")
            result = search_keyword(project_path, keyword, str(args.get("scope")) if args.get("scope") else None)
            return _search_tool_success(tool_name, keyword, result.matches, result.warnings, reason)
        if tool_name == "search_api_path":
            api_path = str(args.get("api_path") or "")
            result = search_api_path(project_path, api_path)
            return _search_tool_success(tool_name, api_path, result.matches, result.warnings, reason, api=api_path)
        if tool_name == "search_symbol":
            symbol = str(args.get("symbol") or "")
            result = search_symbol(project_path, symbol)
            return _search_tool_success(tool_name, symbol, result.matches, result.warnings, reason, symbol=symbol)
        if tool_name == "parse_dependencies":
            result = parse_dependencies(project_path)
            files = ["package.json", "pom.xml", "build.gradle", "build.gradle.kts", *[str(item) for item in result.get("java_config_files", [])]]
            return _tool_success(tool_name, "dependency files", "Parsed dependency metadata.", reason, related_files=files, notes=[_dependency_note(result)])
        if tool_name == "parse_routes":
            routes = parse_routes(project_path)
            files = [str(item.get("file") or "") for item in routes]
            evidence = [
                CodeEvidence(source="tool", file_path=str(item.get("file") or ""), content_summary=f"route={item.get('path')}", relevance_reason=reason)
                for item in routes[:12]
            ]
            return _tool_success(tool_name, "router files", f"Found {len(routes)} route candidates.", reason, related_files=files, code_evidence=evidence)
        if tool_name == "parse_api_calls":
            calls = parse_api_calls(project_path)
            files = [str(item.get("file") or "") for item in calls]
            evidence = [
                CodeEvidence(source="tool", file_path=str(item.get("file") or ""), api=str(item.get("path") or ""), content_summary=f"{item.get('method') or 'UNKNOWN'} {item.get('path')}", relevance_reason=reason)
                for item in calls[:20]
            ]
            return _tool_success(tool_name, "frontend API files", f"Found {len(calls)} frontend API calls.", reason, related_files=files, implementation_path=files, code_evidence=evidence)
        if tool_name == "parse_controller":
            endpoints = parse_controller(project_path)
            files = [str(item.get("backend_file") or "") for item in endpoints]
            evidence = [
                CodeEvidence(source="tool", file_path=str(item.get("backend_file") or ""), api=str(item.get("path") or ""), symbol=str(item.get("backend_method") or "") or None, content_summary=f"{item.get('method') or 'UNKNOWN'} {item.get('path')}", relevance_reason=reason)
                for item in endpoints[:20]
            ]
            return _tool_success(tool_name, "Spring controllers", f"Found {len(endpoints)} controller endpoints.", reason, related_files=files, implementation_path=files, code_evidence=evidence)
        if tool_name == "parse_mapper":
            mappings = parse_mapper(project_path)
            files = [str(item.get("path") or "") for item in mappings]
            evidence = [
                CodeEvidence(source="tool", file_path=str(item.get("path") or ""), content_summary=f"mapper={item.get('kind')}", relevance_reason=reason)
                for item in mappings[:20]
            ]
            return _tool_success(tool_name, "Mapper/Repository files", f"Found {len(mappings)} mapping candidates.", reason, related_files=files, implementation_path=files, code_evidence=evidence)
    except (ReadOnlyToolError, ValueError, OSError) as exc:
        return _tool_error(tool_name, str(args), str(exc), reason)
    return _tool_error(tool_name, str(args), f"Tool is not allowed: {tool_name}", reason)


def _search_tool_success(
    tool_name: str,
    input_summary: str,
    matches: list[Any],
    warnings: list[str],
    reason: str,
    api: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    references = [
        EvidenceRef(path=item.path, reason=reason, source=tool_name, start_line=item.line_number, end_line=item.line_number, excerpt=item.line)
        for item in matches
    ]
    code_evidence = [
        CodeEvidence(
            source="tool",
            file_path=item.path,
            symbol=symbol,
            api=api,
            content_summary=f"Matched line {item.line_number}.",
            code_snippet=item.line,
            relevance_reason=reason,
        )
        for item in matches[:20]
    ]
    return _tool_success(
        tool_name,
        input_summary,
        f"Found {len(matches)} matches.",
        reason,
        references=references,
        related_files=[item.path for item in matches],
        warnings=warnings,
        code_evidence=code_evidence,
    )


def _tool_success(
    tool_name: str,
    input_summary: str,
    output_summary: str,
    reason: str,
    references: list[EvidenceRef] | None = None,
    related_files: list[str] | None = None,
    implementation_path: list[str] | None = None,
    warnings: list[str] | None = None,
    notes: list[str] | None = None,
    code_evidence: list[CodeEvidence] | None = None,
) -> dict[str, Any]:
    return {
        "tool_call": ToolCallRecord(tool_name=tool_name, input_summary=input_summary, output_summary=output_summary, status="success", reason=reason),
        "references": references or [],
        "related_files": related_files or [],
        "implementation_path": implementation_path or [],
        "warnings": warnings or [],
        "notes": notes or [],
        "code_evidence": code_evidence or [],
    }


def _tool_error(tool_name: str, input_summary: str, error: str, reason: str) -> dict[str, Any]:
    return {
        "tool_call": ToolCallRecord(tool_name=tool_name, input_summary=input_summary, output_summary=error, status="error", error=error, reason=reason),
        "warnings": [error],
    }


def _compose_answer(intent: AskIntent, pack: ContextPack, memory: ProjectMemory) -> str:
    files = [item.path for item in pack.relevant_files] or [item.file_path for item in pack.code_evidence if item.file_path]
    apis = [item.path for item in pack.relevant_apis]
    flows = [" -> ".join(item.steps) for item in pack.relevant_flows if item.steps]
    if intent == "project_overview":
        return f"直接回答：{memory.project_name} 的当前理解是：{memory.project_memory.positioning}"
    if intent == "tech_stack":
        stack = "、".join(memory.project_memory.tech_stack) or "当前未识别明确技术栈"
        return f"直接回答：这个项目识别到的主要技术栈是：{stack}。"
    if intent == "config_lookup":
        return "直接回答：配置相关信息需要以配置文件和依赖摘要为准；相关配置文件见下方文件和依据。"
    if intent == "api_lookup":
        if apis:
            return f"直接回答：这个问题优先命中 API Index 中的 {', '.join(apis[:4])}，并已按需搜索前端调用和后端 Controller 证据。"
        return "直接回答：当前 API Index 和代码搜索中没有找到明确接口证据。"
    if intent == "flow_trace":
        if flows:
            return f"直接回答：当前能给出候选实现链路：{flows[0]}。精准跨文件调用链仍以读取到的代码证据为准。"
        return "直接回答：当前代码中未找到明确流程证据。"
    if intent == "file_explanation":
        if files:
            return f"直接回答：{files[0]} 是当前问题最相关的文件；回答基于文件记忆和已读取代码片段。"
        return "直接回答：当前未能从文件记忆或代码搜索中定位到明确文件。"
    if intent == "symbol_lookup":
        symbols = [item.symbol for item in pack.code_evidence if item.symbol]
        if symbols:
            return f"直接回答：当前问题关联到符号 {', '.join(_dedupe_strings(symbols)[:4])}，相关文件和证据见下方。"
        return "直接回答：当前未找到明确符号证据。"
    if intent == "module_explanation":
        if pack.relevant_modules:
            module_text = "；".join(f"{item.name}: {item.responsibility}" for item in pack.relevant_modules[:3])
            return f"直接回答：这个问题关联到这些模块职责：{module_text}"
        return "直接回答：当前项目记忆中没有找到明确模块证据。"
    return "直接回答：我已经围绕这个问题整理了项目记忆、代码索引和只读工具证据；如果证据不足，会在不确定点中说明。"


def _memory_evidence(state: AskState) -> list[CodeEvidence]:
    evidence: list[CodeEvidence] = []
    for item in state.get("relevant_files", [])[:8]:
        evidence.append(
            CodeEvidence(
                source="memory",
                file_path=item.path,
                content_summary=f"{item.role or 'unknown'}: {item.responsibility}",
                relevance_reason="File Summary matched the Ask query or session focus.",
            )
        )
    for item in state.get("relevant_apis", [])[:8]:
        evidence.append(
            CodeEvidence(
                source="memory",
                file_path=item.backend_file or item.frontend_call_file,
                api=item.path,
                content_summary=_api_context(item),
                relevance_reason="API Index matched the Ask query or session focus.",
            )
        )
    for item in state.get("relevant_flows", [])[:5]:
        evidence.append(
            CodeEvidence(
                source="memory",
                file_path=item.evidence_files[0] if item.evidence_files else None,
                content_summary=f"{item.name}: {' -> '.join(item.steps)}",
                relevance_reason="Flow Index matched the Ask query or session focus.",
            )
        )
    return evidence


def _apply_context_budget(pack: ContextPack) -> ContextPack:
    context_text = _render_context_pack(pack)
    if len(context_text) <= CONTEXT_PACK_CHAR_BUDGET:
        return pack.model_copy(update={"context_text": context_text, "truncated": False})

    kept_evidence: list[CodeEvidence] = []
    for evidence in pack.code_evidence:
        candidate = [*kept_evidence, evidence.model_copy(update={"code_snippet": _trim_snippet(evidence.code_snippet or "", 600) or evidence.code_snippet})]
        candidate_pack = pack.model_copy(update={"code_evidence": candidate})
        if len(_render_context_pack(candidate_pack)) > CONTEXT_PACK_CHAR_BUDGET:
            break
        kept_evidence = candidate
    trimmed = pack.model_copy(update={"code_evidence": kept_evidence, "truncated": True})
    return trimmed.model_copy(update={"context_text": _render_context_pack(trimmed)})


def _render_context_pack(pack: ContextPack) -> str:
    sections = [
        "User Question:",
        pack.user_question,
        "Resolved Question:",
        pack.resolved_question,
        "Project Context:",
        pack.project_context,
        "Session Context:",
        pack.session_context,
        "Relevant Modules:",
        "\n".join(f"- {item.name}: {item.responsibility}" for item in pack.relevant_modules),
        "Relevant APIs:",
        "\n".join(f"- {_api_context(item)}" for item in pack.relevant_apis),
        "Relevant Flows:",
        "\n".join(f"- {item.name}: {' -> '.join(item.steps)}" for item in pack.relevant_flows),
        "Code Evidence:",
        "\n".join(_evidence_text(item) for item in pack.code_evidence),
        "Answer Requirements:",
        pack.answer_instructions,
    ]
    return "\n".join(section for section in sections if section)


def _evidence_text(evidence: CodeEvidence) -> str:
    location = evidence.file_path or evidence.api or evidence.symbol or evidence.source
    snippet = f"\n{evidence.code_snippet}" if evidence.code_snippet else ""
    return f"- {location}: {evidence.content_summary} ({evidence.relevance_reason}){snippet}"


def _project_context(memory: ProjectMemory) -> str:
    parts = [
        f"project={memory.project_name}",
        f"description={memory.project_memory.description or memory.project_memory.positioning}",
        f"type={memory.project_memory.project_type or 'unknown'}",
        f"stack={', '.join(memory.project_memory.tech_stack[:10])}",
        f"entry_points={', '.join(memory.project_memory.entry_points[:8])}",
        f"run_commands={', '.join(memory.project_memory.startup_commands[:6])}",
        f"modules={', '.join(memory.project_memory.modules[:8])}",
    ]
    return "\n".join(part for part in parts if part.split("=", 1)[-1])


def _session_context(session_memory: SessionMemory) -> str:
    parts = [
        f"topic={session_memory.current_topic or ''}",
        f"module={session_memory.focused_module or ''}",
        f"files={', '.join(session_memory.focused_files[:8])}",
        f"apis={', '.join(session_memory.focused_apis[:8])}",
        f"flows={', '.join(session_memory.focused_flows[:5])}",
        f"last_question={session_memory.last_question or ''}",
    ]
    return "\n".join(part for part in parts if part.split("=", 1)[-1])


def _rank_modules(memory: ProjectMemory, question: str, resolved: ResolvedQuery) -> list[ModuleMemorySummary]:
    scored = [(_score_text(question, [module.name, module.responsibility, *module.related_files]) + _session_score(module.related_files, resolved.referenced_files), module) for module in memory.module_summaries]
    return [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0][:6]


def _rank_files(memory: ProjectMemory, question: str, resolved: ResolvedQuery, intent_result: IntentResult) -> list[FileMemorySummary]:
    forced = set([*resolved.referenced_files, *intent_result.possible_files])
    scored = [
        (
            _score_text(question, [file.path, file.role, file.responsibility, *file.symbols, *file.related_apis])
            + _session_score([file.path], list(forced))
            + (3 if file.path in forced else 0),
            file,
        )
        for file in memory.file_summaries
    ]
    return [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0][:10]


def _rank_apis(memory: ProjectMemory, question: str, resolved: ResolvedQuery) -> list[ApiIndexEntry]:
    scored = [
        (
            _score_text(question, [entry.path, entry.method or "", entry.backend_method or "", entry.backend_file or "", *entry.frontend_calls])
            + _session_score([entry.path], resolved.referenced_apis),
            entry,
        )
        for entry in memory.api_index
    ]
    return [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0][:8]


def _rank_flows(memory: ProjectMemory, question: str, resolved: ResolvedQuery) -> list[FlowIndexEntry]:
    scored = [
        (
            _score_text(question, [flow.name, flow.kind, flow.description, *flow.steps, *flow.evidence_files])
            + _session_score([flow.name], resolved.referenced_flows),
            flow,
        )
        for flow in memory.flow_index
    ]
    return [item for score, item in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0][:6]


def _matched_file_paths(memory: ProjectMemory, question: str) -> list[str]:
    lowered = question.lower()
    return [
        item.path
        for item in memory.file_summaries
        if item.path.lower() in lowered or _stem(item.path).lower() in lowered or item.path.split("/")[-1].lower() in lowered
    ][:8]


def _matched_api_entries(memory: ProjectMemory, question: str) -> list[ApiIndexEntry]:
    lowered = question.lower()
    return [entry for entry in memory.api_index if entry.path.lower() in lowered or (entry.backend_method and entry.backend_method.lower() in lowered)][:8]


def _matched_symbols(memory: ProjectMemory, question: str) -> list[SymbolIndexItem]:
    lowered = question.lower()
    return [item for item in memory.symbol_index if item.name.lower() in lowered][:8]


def _score_text(question: str, values: list[str]) -> float:
    lowered_question = question.lower()
    keywords = _extract_keywords(question)
    score = 0.0
    for value in values:
        lowered = value.lower()
        if not lowered:
            continue
        if lowered in lowered_question:
            score += 3
        score += sum(1 for keyword in keywords if keyword.lower() in lowered) * 1.2
    return score


def _question_with_hints(question: str, hints: list[QueryHint]) -> str:
    if not hints:
        return question
    keywords = " ".join(hint.keyword for hint in sorted(hints, key=lambda item: item.priority, reverse=True)[:12])
    return f"{question} {keywords}"


def _session_score(values: list[str], session_values: list[str]) -> float:
    wanted = set(session_values)
    return 2.5 if any(value in wanted for value in values) else 0.0


def _extract_keywords(question: str) -> list[str]:
    tokens = re.findall(r"/[A-Za-z0-9_./{}:-]+|[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{2,}", question)
    stopwords = {"用户正在延续上一轮上下文", "当前问题", "这个", "那个", "哪里", "什么", "怎么", "项目"}
    return _dedupe_strings([token.strip() for token in tokens if token.strip() and token.strip() not in stopwords])[:16]


def _is_followup(question: str) -> bool:
    lowered = question.lower()
    return any(marker in lowered for marker in FOLLOWUP_MARKERS)


def _session_files(session_memory: SessionMemory | None) -> list[str]:
    if not session_memory:
        return []
    if session_memory.focused_files:
        return session_memory.focused_files
    if session_memory.turns:
        return session_memory.turns[-1].referenced_files
    return []


def _session_apis(session_memory: SessionMemory | None) -> list[str]:
    if not session_memory:
        return []
    if session_memory.focused_apis:
        return session_memory.focused_apis
    if session_memory.turns:
        return session_memory.turns[-1].referenced_apis
    return []


def _session_flows(session_memory: SessionMemory | None) -> list[str]:
    if not session_memory:
        return []
    if session_memory.focused_flows:
        return session_memory.focused_flows
    if session_memory.turns:
        return session_memory.turns[-1].referenced_flows
    return []


def _last_answer_topic(session_memory: SessionMemory) -> str | None:
    if session_memory.last_answer_summary:
        return session_memory.last_answer_summary[:80]
    if session_memory.turns:
        return session_memory.turns[-1].answer_summary[:80]
    return None


def _files_by_paths(memory: ProjectMemory, paths: list[str]) -> list[FileMemorySummary]:
    wanted = set(paths)
    return [item for item in memory.file_summaries if item.path in wanted]


def _api_context(entry: ApiIndexEntry) -> str:
    parts = [entry.method or "UNKNOWN", entry.path]
    if entry.backend_file:
        parts.append(f"backend={entry.backend_file}")
    if entry.backend_method:
        parts.append(f"handler={entry.backend_method}")
    if entry.frontend_calls:
        parts.append(f"frontend={', '.join(entry.frontend_calls[:4])}")
    return " ".join(parts)


def _line_range(args: dict[str, object]) -> tuple[int, int] | None:
    start = args.get("start_line")
    end = args.get("end_line")
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None


def _search_query(question: str) -> str:
    for token in _extract_keywords(question):
        if token not in {"用户", "正在", "延续", "一轮", "上下文"}:
            return token
    return "Controller"


def _dependency_note(result: dict[str, object]) -> str:
    frontend = result.get("frontend_dependencies")
    java = result.get("java_dependencies")
    return f"依赖摘要: frontend={len(frontend) if isinstance(frontend, dict) else 0}, java={len(java) if isinstance(java, dict) else 0}。"


def _notes_from_code_evidence(evidence: list[CodeEvidence]) -> list[str]:
    notes: list[str] = []
    for item in evidence[:6]:
        location = item.file_path or item.api or item.symbol or item.source
        notes.append(f"{location} 提供了当前回答的依据。")
    return notes


def _append_trace(state: AskState, stage: str, title: str, summary: str) -> list[TraceEvent]:
    events = list(state.get("trace_events", []))
    events.append(TraceEvent(index=len(events) + 1, stage=stage, title=title, summary=summary))
    return events


def _trim_snippet(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[:max_chars].rstrip() + "\n..."


def _stem(path: str) -> str:
    name = path.split("/")[-1]
    return name.rsplit(".", 1)[0]


def _dedupe_strings(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _dedupe_evidence(evidence: list[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[tuple[str, str, str, int | None]] = set()
    unique: list[EvidenceRef] = []
    for item in evidence:
        key = (item.path, item.reason, item.source, item.start_line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_code_evidence(evidence: list[CodeEvidence]) -> list[CodeEvidence]:
    seen: set[tuple[str | None, str | None, str | None, str]] = set()
    unique: list[CodeEvidence] = []
    for item in evidence:
        key = (item.file_path, item.api, item.symbol, item.content_summary)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
