"""LangGraph Ask mode workflow for report-side project questions."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any, NotRequired, TypedDict

try:
    from langgraph.graph import END, StateGraph
except ModuleNotFoundError:  # pragma: no cover - depends on the local runtime.
    END = None
    StateGraph = None  # type: ignore[assignment,misc]

from code_reader_agent.local_state import (
    get_model_settings,
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
    InvestigationFinding,
    InvestigationFlowStep,
    InvestigationPlanItem,
    InvestigationResult,
    InvestigationReview,
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
from code_reader_agent.runtime.llm_client import LLMConfigurationError, LiteLLMClient
from code_reader_agent.skills.registry import KNOWLEDGE_INDEX_VERSION, default_skill_registry
from code_reader_agent.tools.executor import ToolExecutor
from code_reader_agent.tools.models import ToolExecutionContext
from code_reader_agent.tools.registry import default_tool_registry


CONTEXT_PACK_CHAR_BUDGET = 12_000
MAX_TOOL_CALLS = 8
MAX_TOOL_ROUNDS = 3
SESSION_TURN_WINDOW = 8
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


class AskWorkflowError(RuntimeError):
    """Raised when Ask cannot complete its required LangGraph/LLM workflow."""


class AskWorkflowUnavailableError(AskWorkflowError):
    """Raised when LangGraph or the configured LLM is unavailable."""


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
    planned_tool_calls: NotRequired[list[PlannedToolCall]]
    planner_messages: NotRequired[list[dict[str, Any]]]
    pending_tool_call_ids: NotRequired[list[str]]
    tool_rounds: NotRequired[int]
    tool_planning_complete: NotRequired[bool]
    investigation_plan: NotRequired[list[InvestigationPlanItem]]
    investigation_review: NotRequired[InvestigationReview]
    investigation: NotRequired[InvestigationResult]
    investigation_replan_count: NotRequired[int]
    references: NotRequired[list[EvidenceRef]]
    tool_calls: NotRequired[list[ToolCallRecord]]
    code_evidence: NotRequired[list[CodeEvidence]]
    context_pack: NotRequired[ContextPack]
    skill_answer_prompts: NotRequired[list[str]]
    key_code_notes: NotRequired[list[str]]
    answer: NotRequired[str]
    used_llm: NotRequired[bool]
    fallback_used: NotRequired[bool]
    fallback_reason: NotRequired[str | None]
    llm_model: NotRequired[str]
    warnings: NotRequired[list[str]]
    trace_events: NotRequired[list[TraceEvent]]
    persist_session_memory: NotRequired[bool]


def run_ask_mode(
    project_path: str,
    question: str,
    session_memory: SessionMemory | None = None,
    *,
    persist_session_memory: bool = True,
) -> AskModeResult:
    """Run the structured Ask workflow for a project question."""

    _ensure_ask_runtime()
    state = _initial_ask_state(project_path, question, session_memory, persist_session_memory=persist_session_memory)
    state = _compiled_ask_graph().invoke(state)
    return _ask_result_from_state(state)


def run_ask_mode_events(
    project_path: str,
    question: str,
    session_memory: SessionMemory | None = None,
    *,
    persist_session_memory: bool = True,
) -> Iterator[dict[str, Any]]:
    """Run Ask mode and yield public progress events plus the final result."""

    _ensure_ask_runtime()
    state = _initial_ask_state(project_path, question, session_memory, persist_session_memory=persist_session_memory)
    final_state = state
    emitted_trace_count = 0
    emitted_tool_count = 0
    for update in _compiled_ask_graph().stream(state, stream_mode="updates"):
        for node_name, node_state in update.items():
            final_state = node_state
            traces = node_state.get("trace_events", [])
            for trace in traces[emitted_trace_count:]:
                yield {"type": "trace", "node": node_name, "event": trace.model_dump()}
            emitted_trace_count = len(traces)
            if node_name == "LLMToolPlanner" and node_state.get("tool_plan"):
                yield {"type": "tool_plan", "node": node_name, "event": node_state["tool_plan"].model_dump()}
            if node_name == "GoalPlanner":
                yield {"type": "goal_plan", "node": node_name, "event": [item.model_dump() for item in node_state.get("investigation_plan", [])]}
            if node_name == "EvidenceCollector":
                calls = node_state.get("tool_calls", [])
                for call in calls[emitted_tool_count:]:
                    yield {"type": "tool_result", "node": node_name, "event": call.model_dump()}
                emitted_tool_count = len(calls)
            if node_name == "EvidenceReviewer" and node_state.get("investigation_review"):
                review = node_state["investigation_review"]
                yield {"type": "evidence_review", "node": node_name, "event": review.model_dump()}
                if review.needs_more_evidence:
                    yield {"type": "replan", "node": node_name, "event": {"reason": review.stop_reason}}
            if node_name in {"AnswerComposer", "InvestigationReporter"}:
                yield {"type": "answer", "node": node_name, "event": {"answer": node_state.get("answer", "")}}
    yield {"type": "final", "event": _ask_result_from_state(final_state).model_dump()}


def _initial_ask_state(
    project_path: str,
    question: str,
    session_memory: SessionMemory | None = None,
    *,
    persist_session_memory: bool = True,
) -> AskState:
    repo_map = build_repo_map(scan_project(project_path))
    project_memory = get_project_memory(project_path)
    if project_memory is None or project_memory.knowledge_index_version != KNOWLEDGE_INDEX_VERSION:
        project_memory = save_project_memory(build_project_memory(repo_map))
    active_session_memory = session_memory or get_session_memory(project_path) or SessionMemory(project_id=project_id_for_path(project_path))

    return {
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
        "planner_messages": [],
        "investigation_plan": [],
        "investigation_replan_count": 0,
        "pending_tool_call_ids": [],
        "planned_tool_calls": [],
        "tool_rounds": 0,
        "tool_planning_complete": False,
        "persist_session_memory": persist_session_memory,
    }


def _ask_result_from_state(state: AskState) -> AskModeResult:
    project_memory = state["project_memory"]
    return AskModeResult(
        project_id=project_memory.project_id,
        project_name=project_memory.project_name,
        question=state["question"],
        intent=state["intent"],
        answer=state.get("answer", ""),
        resolved_query=state.get("resolved_query"),
        intent_result=state.get("intent_result"),
        investigation=state.get("investigation"),
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
        session_memory=state.get("session_memory", SessionMemory(project_id=project_memory.project_id)),
        warnings=_dedupe_strings(state.get("warnings", [])),
        used_llm=state.get("used_llm", False),
        fallback_used=state.get("fallback_used", False),
        fallback_reason=state.get("fallback_reason"),
        llm_model=state.get("llm_model"),
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


@lru_cache(maxsize=1)
def _compiled_ask_graph() -> Any:
    """Compile the Ask workflow once for the current process."""

    return _build_graph()


def _build_graph() -> Any:
    if StateGraph is None or END is None:
        raise AskWorkflowUnavailableError("langgraph is not installed; Ask requires the compiled LangGraph workflow.")
    graph = StateGraph(AskState)
    graph.add_node("QueryRewriter", _query_rewriter)
    graph.add_node("LLMIntentClassifier", _llm_intent_classifier)
    graph.add_node("SkillRouter", _skill_router)
    graph.add_node("ContextRetriever", _context_retriever)
    graph.add_node("GoalPlanner", _goal_planner)
    graph.add_node("LLMToolPlanner", _llm_tool_planner)
    graph.add_node("EvidenceCollector", _evidence_collector)
    graph.add_node("EvidenceReviewer", _evidence_reviewer)
    graph.add_node("ContextBuilder", _context_builder)
    graph.add_node("AnswerComposer", _answer_composer)
    graph.add_node("InvestigationReporter", _investigation_reporter)
    graph.add_node("MemoryUpdater", _memory_updater)
    graph.add_node("SessionSummarizer", _session_summarizer)
    graph.set_entry_point("QueryRewriter")
    graph.add_edge("QueryRewriter", "LLMIntentClassifier")
    graph.add_edge("LLMIntentClassifier", "SkillRouter")
    graph.add_edge("SkillRouter", "ContextRetriever")
    graph.add_edge("ContextRetriever", "GoalPlanner")
    graph.add_edge("GoalPlanner", "LLMToolPlanner")
    graph.add_conditional_edges(
        "LLMToolPlanner",
        _tool_planning_route,
        {"collect": "EvidenceCollector", "review": "EvidenceReviewer", "build": "ContextBuilder"},
    )
    graph.add_edge("EvidenceCollector", "LLMToolPlanner")
    graph.add_conditional_edges(
        "EvidenceReviewer",
        _evidence_review_route,
        {"replan": "LLMToolPlanner", "build": "ContextBuilder"},
    )
    graph.add_conditional_edges(
        "ContextBuilder",
        _answer_route,
        {"answer": "AnswerComposer", "report": "InvestigationReporter"},
    )
    graph.add_edge("AnswerComposer", "MemoryUpdater")
    graph.add_edge("InvestigationReporter", "MemoryUpdater")
    graph.add_edge("MemoryUpdater", "SessionSummarizer")
    graph.add_edge("SessionSummarizer", END)
    return graph.compile()


def _ensure_ask_runtime() -> None:
    if StateGraph is None:
        raise AskWorkflowUnavailableError("langgraph is not installed; Ask requires LangGraph.")
    _configured_llm_client()


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


def _llm_intent_classifier(state: AskState) -> AskState:
    client = _configured_llm_client()
    prompt = {
        "question": state["resolved_query"].resolved_question,
        "project": _project_context(state["project_memory"]),
        "session": _session_context(state["session_memory"]),
        "allowed_intents": [
            "project_overview", "module_explanation", "file_explanation", "api_lookup", "flow_trace",
            "config_lookup", "tech_stack", "symbol_lookup", "unknown",
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You classify CodeReader Ask questions. Return JSON only matching IntentResult: "
                "intent, keywords, possible_files, possible_apis, possible_symbols, need_code_evidence. "
                "Use only the allowed intent values and make conservative claims."
            ),
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    try:
        intent_result = IntentResult.model_validate(_parse_json_response(_extract_llm_text(client.complete(messages, tools=[]))))
    except Exception as exc:
        raise AskWorkflowError(f"Ask intent classification failed: {exc}") from exc
    return {
        **state,
        "intent": intent_result.intent,
        "intent_result": intent_result,
        "llm_model": client.config.model,
        "trace_events": _append_trace(state, "LLM Intent Classifier", intent_result.intent, f"LLM classified the question as {intent_result.intent}."),
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


def _goal_planner(state: AskState) -> AskState:
    """Create a finite, public evidence plan for feature and flow questions."""

    if state["intent"] != "flow_trace":
        return state

    plan = _flow_investigation_plan(state)
    return {
        **state,
        "investigation_plan": plan,
        "trace_events": _append_trace(
            state,
            "Goal Planner",
            "调查目标规划",
            f"Created {len(plan)} verifiable evidence goals for the requested implementation flow.",
        ),
    }


def _flow_investigation_plan(state: AskState) -> list[InvestigationPlanItem]:
    stack = {item.lower() for item in state["project_memory"].project_memory.tech_stack}
    active_skills = {item.name for item in state["project_memory"].active_skills}
    has_vue = "vue" in stack or "VueSkill" in active_skills
    has_spring = bool({"spring boot", "spring web"} & stack) or "SpringBootSkill" in active_skills
    plan: list[InvestigationPlanItem] = []
    if has_vue:
        plan.extend(
            [
                InvestigationPlanItem(
                    id="frontend_origin",
                    title="定位前端入口或页面",
                    evidence_goal="读取 Vue 路由或页面代码，确认功能从哪个页面或路由进入。",
                ),
                InvestigationPlanItem(
                    id="frontend_request",
                    title="定位前端请求",
                    evidence_goal="读取请求封装或页面代码，确认实际 API 路径或请求调用。",
                ),
            ]
        )
    if has_spring:
        plan.extend(
            [
                InvestigationPlanItem(
                    id="controller",
                    title="定位后端接口入口",
                    evidence_goal="读取 Controller 映射和处理方法，确认接口入口。",
                ),
                InvestigationPlanItem(
                    id="service",
                    title="定位业务服务",
                    evidence_goal="读取 Service 或 Controller 调用，确认业务处理层。",
                ),
                InvestigationPlanItem(
                    id="data_access",
                    title="定位数据访问层",
                    evidence_goal="读取 Mapper、Repository、DAO 或 SQL 映射，确认数据访问候选。",
                ),
            ]
        )
    if not plan:
        plan.append(
            InvestigationPlanItem(
                id="implementation_evidence",
                title="定位实现证据",
                evidence_goal="读取与问题相关的真实源码，确认可追溯实现路径。",
            )
        )
    return plan


def _llm_tool_planner(state: AskState) -> AskState:
    """Ask the LLM whether another bounded batch of safe read tools is needed."""

    used_calls = len(state.get("tool_calls", []))
    rounds = state.get("tool_rounds", 0)
    if rounds >= MAX_TOOL_ROUNDS or used_calls >= MAX_TOOL_CALLS:
        warning = f"LLM tool planning stopped at {rounds} rounds and {used_calls} tool calls."
        return _complete_tool_planning(state, warning)

    client = _configured_llm_client()
    messages = list(state.get("planner_messages", [])) or _initial_tool_planner_messages(state)
    response = _complete_or_raise(client, messages, _ask_tool_schemas(), "tool planning")
    raw_calls = _message_tool_calls(response)
    content = _extract_llm_text(response)
    if not raw_calls:
        return {
            **state,
            "planner_messages": [*messages, _assistant_message_for_history(response, [])],
            "tool_plan": ToolPlan(
                need_tools=False,
                reason="LLM determined that the current evidence is sufficient.",
                tool_calls=state.get("planned_tool_calls", []),
            ),
            "tool_planning_complete": True,
            "tool_rounds": rounds + 1,
            "trace_events": _append_trace(state, "LLM Tool Planner", "工具规划完成", "LLM selected no further read-only tools."),
        }

    available = MAX_TOOL_CALLS - used_calls
    permitted_calls = raw_calls[:available]
    purpose = _public_tool_reason(content, state["intent"])
    planned = [
        PlannedToolCall(
            tool_name=_tool_call_name(item),
            args=_tool_call_arguments(item),
            purpose=purpose,
            priority=MAX_TOOL_CALLS - index,
        )
        for index, item in enumerate(permitted_calls)
    ]
    warnings = list(state.get("warnings", []))
    if len(raw_calls) > len(permitted_calls):
        warnings.append(f"LLM requested {len(raw_calls)} tools, but the {MAX_TOOL_CALLS}-call Ask budget only allowed {len(permitted_calls)}.")
    assistant = _assistant_message_for_history(response, permitted_calls)
    plan = ToolPlan(need_tools=bool(planned), reason=purpose, tool_calls=planned)
    return {
        **state,
        "planner_messages": [*messages, assistant],
        "pending_tool_call_ids": [_tool_call_id(item) for item in permitted_calls],
        "tool_plan": plan,
        "planned_tool_calls": [*state.get("planned_tool_calls", []), *planned],
        "tool_rounds": rounds + 1,
        "warnings": _dedupe_strings(warnings),
        "trace_events": _append_trace(state, "LLM Tool Planner", "只读工具计划", f"LLM planned {len(planned)} safe read-only tool calls in round {rounds + 1}."),
    }


def _complete_tool_planning(state: AskState, warning: str) -> AskState:
    return {
        **state,
        "tool_plan": ToolPlan(need_tools=False, reason=warning, tool_calls=state.get("planned_tool_calls", [])),
        "tool_planning_complete": True,
        "warnings": _dedupe_strings([*state.get("warnings", []), warning]),
        "trace_events": _append_trace(state, "LLM Tool Planner", "工具预算已用尽", warning),
    }


def _tool_planning_route(state: AskState) -> str:
    if state.get("tool_plan", ToolPlan(need_tools=False, reason="")).need_tools:
        return "collect"
    if state.get("intent") == "flow_trace":
        return "review"
    return "build"


def _evidence_collector(state: AskState) -> AskState:
    references = list(state.get("references", []))
    tool_calls = list(state.get("tool_calls", []))
    related_files = list(state.get("related_files", []))
    implementation_path = list(state.get("implementation_path", []))
    warnings = list(state.get("warnings", []))
    code_evidence = list(state.get("code_evidence", []))
    notes = list(state.get("key_code_notes", []))
    planner_messages = list(state.get("planner_messages", []))
    pending_ids = list(state.get("pending_tool_call_ids", []))
    executor = ToolExecutor()
    execution_context = ToolExecutionContext(
        project_path=state["project_path"],
        mode="ask",
        allowed_permissions=["read"],
        project_memory=state["project_memory"],
    )

    for index, planned in enumerate(state.get("tool_plan", ToolPlan(need_tools=False, reason="")).tool_calls):
        result = executor.execute(planned, execution_context)
        if result.tool_call:
            tool_calls.append(result.tool_call)
        references.extend(result.references)
        related_files.extend(result.related_files)
        implementation_path.extend(result.implementation_path)
        warnings.extend(result.warnings)
        code_evidence.extend(result.evidence)
        notes.extend(result.notes)
        planner_messages.append(
            {
                "role": "tool",
                "tool_call_id": pending_ids[index] if index < len(pending_ids) else f"ask-tool-{index}",
                "content": json.dumps(_tool_result_for_planner(result), ensure_ascii=False),
            }
        )

    return {
        **state,
        "references": _dedupe_evidence(references),
        "tool_calls": tool_calls,
        "related_files": _dedupe_strings(related_files),
        "implementation_path": _dedupe_strings(implementation_path),
        "warnings": _dedupe_strings(warnings),
        "code_evidence": _dedupe_code_evidence(code_evidence),
        "key_code_notes": _dedupe_strings(notes),
        "planner_messages": planner_messages,
        "pending_tool_call_ids": [],
        "trace_events": _append_trace(state, "Evidence Collector", "工具执行", f"Executed {len(state.get('tool_plan', ToolPlan(need_tools=False, reason='')).tool_calls)} read-only tool calls."),
    }


def _evidence_reviewer(state: AskState) -> AskState:
    """Judge flow-plan coverage from fresh tool evidence before a final report."""

    plan = list(state.get("investigation_plan", []))
    fresh_evidence = [item for item in state.get("code_evidence", []) if item.source == "tool"]
    satisfied_ids = [item.id for item in plan if _goal_has_evidence(item.id, fresh_evidence)]
    reviewed_plan = [
        item.model_copy(update={"status": "satisfied" if item.id in satisfied_ids else "missing"})
        for item in plan
    ]
    missing = [item.evidence_goal for item in reviewed_plan if item.status == "missing"]
    used_calls = len(state.get("tool_calls", []))
    rounds = state.get("tool_rounds", 0)
    can_replan = bool(missing) and used_calls < MAX_TOOL_CALLS and rounds < MAX_TOOL_ROUNDS
    if not missing:
        stop_reason = "所有预设流程阶段均已获得实时代码证据。"
    elif can_replan:
        stop_reason = "关键流程阶段仍缺少证据，Agent 将继续规划只读工具调用。"
    else:
        stop_reason = "工具预算已用尽或没有剩余调查轮次，保留当前部分结论。"
    review = InvestigationReview(
        satisfied_goal_ids=satisfied_ids,
        missing_evidence=missing,
        needs_more_evidence=can_replan,
        stop_reason=stop_reason,
        next_step="围绕缺失阶段读取关联源码。" if can_replan else None,
    )
    warnings = list(state.get("warnings", []))
    if missing and not can_replan:
        warnings.append("功能/流程调查未获得全部关键代码证据，结果将标记为部分完成。")
    return {
        **state,
        "investigation_plan": reviewed_plan,
        "investigation_review": review,
        "investigation_replan_count": state.get("investigation_replan_count", 0) + int(can_replan),
        "planner_messages": (
            [
                *state.get("planner_messages", []),
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "investigation_review": review.model_dump(),
                            "instruction": "Continue the investigation by collecting evidence for the listed missing goals.",
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            if can_replan
            else state.get("planner_messages", [])
        ),
        "warnings": _dedupe_strings(warnings),
        "trace_events": _append_trace(
            state,
            "Evidence Reviewer",
            "证据覆盖审查",
            f"Satisfied {len(satisfied_ids)}/{len(reviewed_plan)} investigation goals; {'replanning' if can_replan else 'reporting'} next.",
        ),
    }


def _evidence_review_route(state: AskState) -> str:
    review = state.get("investigation_review")
    return "replan" if review and review.needs_more_evidence else "build"


def _goal_has_evidence(goal_id: str, evidence: list[CodeEvidence]) -> bool:
    for item in evidence:
        path = (item.file_path or "").lower()
        text = " ".join([item.content_summary, item.code_snippet or "", item.api or ""]).lower()
        if goal_id == "frontend_origin" and (path.endswith(".vue") or "/router/" in path or "path:" in text):
            return True
        if goal_id == "frontend_request" and ("/api/" in text or any(token in text for token in ("fetch(", "axios", "request("))):
            return True
        if goal_id == "controller" and (path.endswith("controller.java") or "@getmapping" in text or "@postmapping" in text or "@requestmapping" in text):
            return True
        if goal_id == "service" and (path.endswith("service.java") or "@service" in text or " service" in text):
            return True
        if goal_id == "data_access" and (
            path.endswith(("mapper.java", "repository.java", "dao.java", "mapper.xml"))
            or any(token in text for token in ("@mapper", " mapper", " repository", "<select"))
        ):
            return True
        if goal_id == "implementation_evidence" and item.file_path:
            return True
    return False


def _answer_route(state: AskState) -> str:
    return "report" if state.get("intent") == "flow_trace" else "answer"


def _investigation_reporter(state: AskState) -> AskState:
    """Create a deterministic, evidence-only report for a flow investigation."""

    plan = list(state.get("investigation_plan", []))
    review = state.get("investigation_review", InvestigationReview(stop_reason="调查未完成证据审查。"))
    evidence = [item for item in state.get("code_evidence", []) if item.source == "tool"]
    references = state.get("references", [])
    findings = [_finding_for_goal(item, evidence, references) for item in plan]
    steps = _investigation_flow_steps(plan, evidence, references)
    confirmed_steps = [item for item in steps if item.status == "confirmed"]
    complete = not review.missing_evidence and bool(steps) and len(confirmed_steps) == len(steps)
    status = "complete" if complete else "partial"
    investigation = InvestigationResult(
        goal=state["question"],
        status=status,
        plan=plan,
        flow_steps=steps,
        findings=findings,
        review=review,
    )
    answer = _investigation_answer(investigation)
    return {
        **state,
        "investigation": investigation,
        "answer": answer,
        "used_llm": True,
        "fallback_used": False,
        "fallback_reason": None,
        "trace_events": _append_trace(
            state,
            "Investigation Reporter",
            "调查报告交付",
            f"Delivered a {status} evidence-backed implementation-flow report with {len(confirmed_steps)} confirmed relationships.",
        ),
    }


def _finding_for_goal(
    goal: InvestigationPlanItem,
    evidence: list[CodeEvidence],
    references: list[EvidenceRef],
) -> InvestigationFinding:
    supporting = [item for item in evidence if _goal_has_evidence(goal.id, [item])]
    refs = _references_for_evidence(supporting, references)
    if supporting and refs:
        paths = ", ".join(_dedupe_strings([item.path for item in refs])[:2])
        return InvestigationFinding(
            title=goal.title,
            statement=f"已从 {paths} 读取到满足该调查目标的代码证据。",
            status="confirmed",
            confidence=1.0,
            evidence=refs,
        )
    return InvestigationFinding(
        title=goal.title,
        statement="当前尚未读取到足以确认该流程阶段的代码证据。",
        status="unconfirmed",
        missing_evidence=[goal.evidence_goal],
    )


def _investigation_flow_steps(
    plan: list[InvestigationPlanItem],
    evidence: list[CodeEvidence],
    references: list[EvidenceRef],
) -> list[InvestigationFlowStep]:
    ordered_ids = [item.id for item in plan if item.status == "satisfied"]
    labels = {
        "frontend_origin": "Vue 页面或路由",
        "frontend_request": "前端 API 请求",
        "controller": "Spring Controller",
        "service": "Spring Service",
        "data_access": "Mapper / Repository",
        "implementation_evidence": "相关实现源码",
    }
    relations = {
        ("frontend_origin", "frontend_request"): "页面或路由触发请求调用",
        ("frontend_request", "controller"): "请求路径到达后端接口",
        ("controller", "service"): "接口处理方法委托业务服务",
        ("service", "data_access"): "业务服务调用数据访问层",
    }
    steps: list[InvestigationFlowStep] = []
    for source_id, target_id in zip(ordered_ids, ordered_ids[1:]):
        source_evidence = [item for item in evidence if _goal_has_evidence(source_id, [item])]
        target_evidence = [item for item in evidence if _goal_has_evidence(target_id, [item])]
        link_evidence = _link_evidence(source_id, target_id, source_evidence, target_evidence)
        refs = _references_for_evidence(link_evidence, references)
        steps.append(
            InvestigationFlowStep(
                source=labels.get(source_id, source_id),
                target=labels.get(target_id, target_id),
                relation=relations.get((source_id, target_id), "按已读取阶段形成的候选实现顺序"),
                status="confirmed" if refs else "unconfirmed",
                evidence=refs,
            )
        )
    return steps


def _link_evidence(
    source_id: str,
    target_id: str,
    source_evidence: list[CodeEvidence],
    target_evidence: list[CodeEvidence],
) -> list[CodeEvidence]:
    source_text = "\n".join(item.code_snippet or "" for item in source_evidence).lower()
    target_text = "\n".join(item.code_snippet or "" for item in target_evidence).lower()
    if (source_id, target_id) == ("frontend_origin", "frontend_request"):
        return source_evidence if any(token in source_text for token in ("fetch(", "axios", "request(", "/api/")) else []
    if (source_id, target_id) == ("frontend_request", "controller"):
        shared_paths = set(_api_paths_from_text(source_text)) & set(_api_paths_from_text(target_text))
        return [*source_evidence, *target_evidence] if shared_paths else []
    if (source_id, target_id) == ("controller", "service"):
        return source_evidence if "service" in source_text else []
    if (source_id, target_id) == ("service", "data_access"):
        return source_evidence if any(token in source_text for token in ("mapper", "repository", "dao")) else []
    return []


def _api_paths_from_text(text: str) -> list[str]:
    return re.findall(r"/[a-z0-9_./{}:-]+", text)


def _references_for_evidence(evidence: list[CodeEvidence], references: list[EvidenceRef]) -> list[EvidenceRef]:
    paths = {item.file_path for item in evidence if item.file_path}
    return _dedupe_evidence([item for item in references if item.path in paths])[:4]


def _investigation_answer(investigation: InvestigationResult) -> str:
    confirmed = [item for item in investigation.findings if item.status == "confirmed"]
    lines = [f"调查结论：本次功能/流程调查为{('完整' if investigation.status == 'complete' else '部分')}完成。"]
    if confirmed:
        lines.append("已确认阶段：" + "；".join(item.title for item in confirmed) + "。")
    if investigation.review.missing_evidence:
        lines.append("未确认断点：" + "；".join(investigation.review.missing_evidence) + "。")
    if investigation.flow_steps:
        lines.append("流程关系：" + " → ".join([investigation.flow_steps[0].source, *[item.target for item in investigation.flow_steps]]) + "。")
    return "\n".join(lines)


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
    client = _configured_llm_client()
    messages = [
        {
            "role": "system",
            "content": (
                "You are CodeReader Agent Ask mode. Answer in Chinese using only the Context Pack and evidence. "
                "Do not claim a complete call chain unless the evidence supports it. State uncertainty clearly."
            ),
        },
        {
            "role": "user",
            "content": "\n".join([f"Intent: {state['intent']}", "Context Pack:", pack.context_text, "Answer requirements:", pack.answer_instructions]),
        },
    ]
    answer = _extract_llm_text(_complete_or_raise(client, messages, [], "answer composition")).strip()
    if not answer:
        raise AskWorkflowError("Ask answer composition failed: LLM returned an empty answer.")
    notes = list(state.get("key_code_notes", []))
    warnings = list(state.get("warnings", []))
    if _requires_fresh_code_evidence(state) and not _has_fresh_tool_evidence(state):
        warnings.append("项目认知可能过期，当前工作区未找到可用于确认该问题的实时代码证据。")
    if pack.code_evidence:
        notes.extend(_notes_from_code_evidence(pack.code_evidence))
    else:
        notes.append("当前代码中未找到明确证据。")
    return {
        **state,
        "answer": answer,
        "used_llm": True,
        "fallback_used": False,
        "fallback_reason": None,
        "llm_model": client.config.model,
        "warnings": _dedupe_strings(warnings),
        "key_code_notes": _dedupe_strings(notes),
        "trace_events": _append_trace(
            state,
            "Answer Composer",
            "LLM 证据化回答",
            "Composed answer with the LLM from the evidence-grounded Context Pack.",
        ),
    }


def _extract_llm_text(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                return content if isinstance(content, str) else ""
        return ""
    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        return content if isinstance(content, str) else ""
    return ""


def _configured_llm_client() -> LiteLLMClient:
    client = LiteLLMClient(model=get_model_settings().model)
    if not client.is_configured():
        missing = " or ".join(client.missing_environment_variables())
        raise AskWorkflowUnavailableError(f"Ask LLM is not configured: missing {missing}.")
    return client


def _complete_or_raise(client: LiteLLMClient, messages: list[dict[str, Any]], tools: list[dict[str, Any]], stage: str) -> Any:
    try:
        return client.complete(messages, tools=tools)
    except LLMConfigurationError as exc:
        raise AskWorkflowUnavailableError(f"Ask {stage} is unavailable: {exc}") from exc
    except Exception as exc:
        raise AskWorkflowError(f"Ask {stage} failed: {exc}") from exc


def _parse_json_response(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        value = value.rsplit("```", 1)[0].strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")
    return parsed


def _ask_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in default_tool_registry().list_tools_by_mode("ask")
        if tool.permission == "read" and tool.risk_level == "safe"
    ]


def _initial_tool_planner_messages(state: AskState) -> list[dict[str, Any]]:
    payload = {
        "intent": state["intent"],
        "resolved_question": state["resolved_query"].resolved_question,
        "project_context": _project_context(state["project_memory"]),
        "session_context": _session_context(state["session_memory"]),
        "retrieved_context": state.get("retrieved_context", [])[:20],
        "related_files": state.get("related_files", [])[:12],
        "related_apis": state.get("related_apis", [])[:8],
        "skill_hints": [item.model_dump() for item in state.get("query_hints", [])[:12]],
        "investigation_plan": [item.model_dump() for item in state.get("investigation_plan", [])],
        "investigation_review": state["investigation_review"].model_dump() if state.get("investigation_review") else None,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the CodeReader Ask tool planner. Decide whether safe read-only tools are needed to answer the "
                "question with evidence. Use only supplied function tools. Before calling tools, return at most one short "
                "public reason sentence; do not reveal hidden reasoning. When evidence is sufficient, call no tool."
                " For flow investigations, satisfy the listed evidence goals before stopping; after a review identifies gaps, "
                "choose tools that read the missing implementation stage."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _message_tool_calls(response: Any) -> list[Any]:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        return list(message.get("tool_calls") or []) if isinstance(message, dict) else []
    choices = getattr(response, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    return list(getattr(message, "tool_calls", None) or [])


def _tool_call_id(tool_call: Any) -> str:
    value = tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
    return str(value or "ask-tool")


def _tool_call_name(tool_call: Any) -> str:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    return str(function.get("name") if isinstance(function, dict) else getattr(function, "name", "") or "")


def _tool_call_arguments(tool_call: Any) -> dict[str, object]:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    raw = function.get("arguments") if isinstance(function, dict) else getattr(function, "arguments", "{}")
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _assistant_message_for_history(response: Any, tool_calls: list[Any]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": _extract_llm_text(response) or None}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": _tool_call_id(call),
                "type": "function",
                "function": {"name": _tool_call_name(call), "arguments": json.dumps(_tool_call_arguments(call), ensure_ascii=False)},
            }
            for call in tool_calls
        ]
    return message


def _public_tool_reason(content: str, intent: AskIntent) -> str:
    text = " ".join(content.strip().split())
    if text:
        return text[:240]
    return f"LLM 根据 {intent} 意图决定调用只读工具补充可验证代码证据。"


def _tool_result_for_planner(result: Any) -> dict[str, Any]:
    return {
        "tool_name": result.tool_name,
        "success": result.success,
        "output_summary": result.output_summary,
        "related_files": result.related_files[:12],
        "evidence": [item.model_dump() for item in result.evidence[:8]],
        "warnings": result.warnings[:8],
        "error": result.error,
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
            "turns": [*session_memory.turns, turn],
        }
    )
    return {
        **state,
        "session_memory": updated,
        "trace_events": _append_trace(state, "Memory Updater", "Session Memory", f"Prepared {len(updated.turns)} Ask turns for persistence."),
    }


def _session_summarizer(state: AskState) -> AskState:
    """Persist a compact LLM summary once the active turn window overflows."""

    session_memory = state["session_memory"]
    overflow = session_memory.turns[:-SESSION_TURN_WINDOW]
    retained_turns = session_memory.turns[-SESSION_TURN_WINDOW:]
    warnings = list(state.get("warnings", []))
    summary = session_memory.history_summary
    if overflow:
        try:
            summary = _summarize_session_history(session_memory.history_summary, overflow)
        except AskWorkflowError as exc:
            warnings.append(f"Session history summary failed; older turns were removed: {exc}")
        session_memory = session_memory.model_copy(
            update={
                "history_summary": summary,
                "archived_turn_count": session_memory.archived_turn_count + len(overflow),
                "turns": retained_turns,
            }
        )
    if state.get("persist_session_memory", True):
        session_memory = save_session_memory(session_memory)
    return {
        **state,
        "session_memory": session_memory,
        "warnings": _dedupe_strings(warnings),
        "trace_events": _append_trace(
            state,
            "Session Summarizer",
            "会话摘要",
            f"Archived {len(overflow)} turns; retained {len(session_memory.turns)} recent turns.",
        ),
    }


def _summarize_session_history(existing_summary: str | None, turns: list[SessionMemoryTurn]) -> str:
    client = _configured_llm_client()
    payload = {
        "existing_summary": existing_summary or "",
        "archived_turns": [turn.model_dump() for turn in turns],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Summarize archived CodeReader Ask turns in Chinese. Preserve confirmed topics, files, APIs, flows, "
                "and unresolved uncertainty. Do not invent code facts. Return concise plain text only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    summary = _extract_llm_text(_complete_or_raise(client, messages, [], "session summarization")).strip()
    if not summary:
        raise AskWorkflowError("LLM returned an empty session history summary.")
    return summary[:2_000]


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
        f"history_summary={session_memory.history_summary or ''}",
        f"archived_turn_count={session_memory.archived_turn_count}",
        f"topic={session_memory.current_topic or ''}",
        f"module={session_memory.focused_module or ''}",
        f"files={', '.join(session_memory.focused_files[:8])}",
        f"apis={', '.join(session_memory.focused_apis[:8])}",
        f"flows={', '.join(session_memory.focused_flows[:5])}",
        f"last_question={session_memory.last_question or ''}",
        "recent_turns=" + " | ".join(
            f"{turn.intent}: {turn.question[:80]} => {turn.answer_summary[:120]}"
            for turn in session_memory.turns[-SESSION_TURN_WINDOW:]
        ),
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


def _search_query(question: str) -> str:
    for token in _extract_keywords(question):
        if token not in {"用户", "正在", "延续", "一轮", "上下文"}:
            return token
    return "Controller"


def _notes_from_code_evidence(evidence: list[CodeEvidence]) -> list[str]:
    notes: list[str] = []
    for item in evidence[:6]:
        location = item.file_path or item.api or item.symbol or item.source
        notes.append(f"{location} 提供了当前回答的依据。")
    return notes


def _requires_fresh_code_evidence(state: AskState) -> bool:
    intent = state.get("intent")
    if intent in {"file_explanation", "module_explanation", "api_lookup", "flow_trace", "symbol_lookup", "config_lookup"}:
        return True
    intent_result = state.get("intent_result")
    return bool(intent_result and intent_result.need_code_evidence)


def _has_fresh_tool_evidence(state: AskState) -> bool:
    return any(item.source == "tool" for item in state.get("code_evidence", []))


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
