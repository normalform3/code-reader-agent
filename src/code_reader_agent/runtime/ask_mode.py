"""LangGraph Ask mode workflow for report-side project questions."""

from __future__ import annotations

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
    EvidenceRef,
    FlowIndexEntry,
    ModuleMemorySummary,
    ProjectMemory,
    SessionMemory,
    SessionMemoryTurn,
    ToolCallRecord,
    TraceEvent,
)
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import scan_project
from code_reader_agent.tools.read_only import (
    ReadOnlyToolError,
    list_files,
    parse_api_calls,
    parse_controller,
    parse_dependencies,
    parse_mapper,
    parse_routes,
    read_file,
    search_code,
    search_symbol,
)


class AskState(TypedDict):
    project_path: str
    question: str
    project_memory: ProjectMemory
    session_memory: SessionMemory
    intent: NotRequired[AskIntent]
    retrieved_context: NotRequired[list[str]]
    related_files: NotRequired[list[str]]
    related_apis: NotRequired[list[str]]
    implementation_path: NotRequired[list[str]]
    tool_plan: NotRequired[list[dict[str, Any]]]
    references: NotRequired[list[EvidenceRef]]
    tool_calls: NotRequired[list[ToolCallRecord]]
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
    if project_memory is None:
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
            "related_files": [],
            "related_apis": [],
            "implementation_path": [],
            "tool_plan": [],
            "references": [],
            "tool_calls": [],
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

    lowered = question.lower()
    if any(keyword in lowered for keyword in ("技术栈", "框架", "framework", "dependencies", "依赖")):
        return "tech_stack"
    if any(keyword in lowered for keyword in ("配置", "数据库", "application.yml", "application.properties", ".env", "pom.xml", "package.json")):
        return "configuration"
    if any(keyword in lowered for keyword in ("调用链", "流程", "怎么走", "登录流程", "认证流程", "auth flow")):
        return "call_chain"
    if any(keyword in lowered for keyword in ("接口", "api", "endpoint", "在哪里被调用", "where is this called")):
        return "api_usage"
    if _mentions_file(question, project_memory) or any(keyword in question for keyword in ("文件", "Controller", "Service", ".vue", ".ts", ".java")):
        return "file_explanation"
    if any(keyword in lowered for keyword in ("模块", "权限", "登录", "认证", "module", "实现")):
        return "module_explanation"
    if session_memory and session_memory.turns and any(keyword in lowered for keyword in ("这个", "它", "那里", "上面", "刚才")):
        previous = session_memory.turns[-1].intent
        if previous in {"api_usage", "call_chain", "file_explanation", "module_explanation"}:
            return previous
    return "project_overview"


def _build_graph() -> Any:
    graph = StateGraph(AskState)
    graph.add_node("IntentClassifier", _intent_classifier)
    graph.add_node("ContextRetriever", _context_retriever)
    graph.add_node("ToolPlanner", _tool_planner)
    graph.add_node("EvidenceCollector", _evidence_collector)
    graph.add_node("AnswerComposer", _answer_composer)
    graph.add_node("MemoryUpdater", _memory_updater)
    graph.set_entry_point("IntentClassifier")
    graph.add_edge("IntentClassifier", "ContextRetriever")
    graph.add_edge("ContextRetriever", "ToolPlanner")
    graph.add_edge("ToolPlanner", "EvidenceCollector")
    graph.add_edge("EvidenceCollector", "AnswerComposer")
    graph.add_edge("AnswerComposer", "MemoryUpdater")
    graph.add_edge("MemoryUpdater", END)
    return graph.compile()


def _intent_classifier(state: AskState) -> AskState:
    intent = classify_ask_intent(state["question"], state["project_memory"], state.get("session_memory"))
    return {
        **state,
        "intent": intent,
        "trace_events": _append_trace(state, "Intent Classifier", intent, f"Question classified as {intent}."),
    }


def _context_retriever(state: AskState) -> AskState:
    memory = state["project_memory"]
    intent = state["intent"]
    question = state["question"]
    related_files: list[str] = []
    related_apis: list[str] = []
    implementation_path: list[str] = []
    context: list[str] = []

    if intent == "project_overview":
        context.extend(
            [
                memory.project_memory.positioning,
                f"技术栈: {', '.join(memory.project_memory.tech_stack) or '未识别明确技术栈'}",
                f"模块: {', '.join(memory.project_memory.modules) or '暂无模块'}",
            ]
        )
        related_files.extend(_top_files(memory))
    elif intent == "tech_stack":
        context.extend(memory.project_memory.tech_stack)
        related_files.extend(_config_files(memory))
    elif intent == "configuration":
        related_files.extend(_config_files(memory))
        context.extend(f"{item.path}: {item.responsibility}" for item in _files_by_paths(memory, related_files))
    elif intent == "module_explanation":
        modules = _matched_modules(memory, question)
        if not modules:
            modules = _auth_modules(memory) or memory.module_summaries[:3]
        for module in modules:
            context.append(f"{module.name}: {module.responsibility}")
            related_files.extend(module.related_files)
        implementation_path.extend(related_files)
    elif intent == "file_explanation":
        files = _matched_files(memory, question) or _previous_files(state.get("session_memory"))
        related_files.extend(files[:6])
        context.extend(f"{item.path}: {item.responsibility}" for item in _files_by_paths(memory, related_files))
    elif intent == "api_usage":
        entries = _matched_api_entries(memory, question) or _previous_api_entries(memory, state.get("session_memory")) or memory.api_index[:5]
        for entry in entries:
            related_apis.append(entry.path)
            if entry.backend_file:
                related_files.append(entry.backend_file)
            related_files.extend(entry.frontend_calls)
            implementation_path.extend([*entry.frontend_calls, entry.backend_file or ""])
            context.append(_api_context(entry))
    elif intent == "call_chain":
        flows = _matched_flows(memory, question) or memory.flow_index[:3]
        for flow in flows:
            context.append(f"{flow.name}: {' -> '.join(flow.steps)}")
            related_files.extend(flow.evidence_files)
            implementation_path.extend(flow.steps)

    if not related_files:
        related_files.extend(_previous_files(state.get("session_memory")))

    return {
        **state,
        "retrieved_context": _dedupe_strings(context),
        "related_files": _dedupe_strings(related_files),
        "related_apis": _dedupe_strings(related_apis),
        "implementation_path": _dedupe_strings(implementation_path),
        "trace_events": _append_trace(
            state,
            "Context Retriever",
            "Project memory lookup",
            f"Retrieved {len(context)} context items and {len(related_files)} related files.",
        ),
    }


def _tool_planner(state: AskState) -> AskState:
    intent = state["intent"]
    question = state["question"]
    related_files = state.get("related_files", [])
    related_apis = state.get("related_apis", [])
    plan: list[dict[str, Any]] = []

    if intent == "project_overview":
        if not state.get("retrieved_context"):
            plan.append({"tool": "list_files", "args": {"max_depth": 2}, "reason": "项目记忆不足，补充目录结构。"})
    elif intent == "tech_stack":
        plan.append({"tool": "parse_dependencies", "args": {}, "reason": "确认依赖文件和技术栈证据。"})
    elif intent == "configuration":
        plan.append({"tool": "parse_dependencies", "args": {}, "reason": "读取配置和依赖摘要。"})
        for path in related_files[:4]:
            plan.append({"tool": "read_file", "args": {"relative_path": path, "start_line": 1, "end_line": 80}, "reason": "读取配置文件片段作为依据。"})
    elif intent == "file_explanation":
        for path in related_files[:3]:
            plan.append({"tool": "read_file", "args": {"relative_path": path, "start_line": 1, "end_line": 120}, "reason": "用户询问指定文件，需要读取真实代码片段。"})
        if not related_files:
            plan.append({"tool": "search_symbol", "args": {"symbol": question}, "reason": "未在文件记忆中定位文件，按符号搜索。"})
    elif intent == "module_explanation":
        for path in related_files[:4]:
            plan.append({"tool": "read_file", "args": {"relative_path": path, "start_line": 1, "end_line": 100}, "reason": "读取模块关键文件补充证据。"})
        plan.append({"tool": "search_keyword", "args": {"query": _search_query(question)}, "reason": "搜索模块相关关键词补足上下文。"})
    elif intent == "api_usage":
        plan.extend(
            [
                {"tool": "parse_api_calls", "args": {}, "reason": "提取前端 axios/fetch/request 调用候选。"},
                {"tool": "parse_controller", "args": {}, "reason": "提取 Spring Controller 接口候选。"},
            ]
        )
        for api in related_apis[:2]:
            plan.append({"tool": "search_keyword", "args": {"query": api}, "reason": "搜索接口路径在哪里被调用。"})
    elif intent == "call_chain":
        for path in related_files[:5]:
            plan.append({"tool": "read_file", "args": {"relative_path": path, "start_line": 1, "end_line": 100}, "reason": "读取流程关键文件作为链路依据。"})
        plan.append({"tool": "search_keyword", "args": {"query": _search_query(question)}, "reason": "搜索流程关键词补充链路候选。"})

    return {
        **state,
        "tool_plan": plan[:8],
        "trace_events": _append_trace(state, "Tool Planner", "Read-only tool plan", f"Planned {len(plan[:8])} tool calls."),
    }


def _evidence_collector(state: AskState) -> AskState:
    references = list(state.get("references", []))
    tool_calls = list(state.get("tool_calls", []))
    related_files = list(state.get("related_files", []))
    implementation_path = list(state.get("implementation_path", []))
    warnings = list(state.get("warnings", []))
    notes = list(state.get("key_code_notes", []))

    for plan in state.get("tool_plan", []):
        tool_name = str(plan.get("tool") or "")
        args = plan.get("args") if isinstance(plan.get("args"), dict) else {}
        reason = str(plan.get("reason") or "")
        result = _execute_ask_tool(state["project_path"], tool_name, args, reason)
        tool_calls.append(result["tool_call"])
        references.extend(result.get("references", []))
        related_files.extend(result.get("related_files", []))
        implementation_path.extend(result.get("implementation_path", []))
        warnings.extend(result.get("warnings", []))
        notes.extend(result.get("notes", []))

    return {
        **state,
        "references": _dedupe_evidence(references),
        "tool_calls": tool_calls,
        "related_files": _dedupe_strings(related_files),
        "implementation_path": _dedupe_strings(implementation_path),
        "warnings": _dedupe_strings(warnings),
        "key_code_notes": _dedupe_strings(notes),
        "trace_events": _append_trace(state, "Evidence Collector", "Tool execution", f"Executed {len(state.get('tool_plan', []))} read-only tool calls."),
    }


def _answer_composer(state: AskState) -> AskState:
    answer = _compose_answer(
        intent=state["intent"],
        question=state["question"],
        memory=state["project_memory"],
        context=state.get("retrieved_context", []),
        related_files=state.get("related_files", []),
        implementation_path=state.get("implementation_path", []),
        references=state.get("references", []),
    )
    notes = list(state.get("key_code_notes", []))
    if state.get("references"):
        notes.extend(_notes_from_references(state["references"]))
    elif state.get("related_files"):
        notes.append("当前回答主要来自 Project Memory；如需确认具体实现，Ask 模式会继续读取相关文件。")
    else:
        notes.append("当前代码中未找到明确证据。")
    return {
        **state,
        "answer": answer,
        "key_code_notes": _dedupe_strings(notes),
        "trace_events": _append_trace(state, "Answer Composer", "Evidence-grounded answer", "Composed answer with files, path, and references."),
    }


def _memory_updater(state: AskState) -> AskState:
    session_memory = state["session_memory"]
    turn = SessionMemoryTurn(
        question=state["question"],
        intent=state["intent"],
        referenced_files=_dedupe_strings(state.get("related_files", []))[:12],
        referenced_apis=_dedupe_strings(state.get("related_apis", []))[:12],
        answer_summary=str(state.get("answer") or "")[:240],
    )
    updated = session_memory.model_copy(update={"turns": [*session_memory.turns[-8:], turn]})
    updated = save_session_memory(updated)
    return {
        **state,
        "session_memory": updated,
        "trace_events": _append_trace(state, "Memory Updater", "Session memory", f"Stored {len(updated.turns)} Ask turns."),
    }


def _execute_ask_tool(project_path: str, tool_name: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
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
                excerpt=result.content,
            )
            return _tool_success(
                tool_name,
                result.path,
                f"Read lines {result.start_line}-{result.end_line}.",
                reason,
                references=[evidence],
                related_files=[result.path],
                warnings=result.warnings,
            )
        if tool_name == "search_keyword":
            query = str(args.get("query") or "")
            result = search_code(project_path, query)
            references = [
                EvidenceRef(path=item.path, reason=reason, source="search_keyword", start_line=item.line_number, end_line=item.line_number, excerpt=item.line)
                for item in result.matches
            ]
            return _tool_success(tool_name, query, f"Found {len(result.matches)} matches.", reason, references=references, related_files=[item.path for item in result.matches], warnings=result.warnings)
        if tool_name == "search_symbol":
            symbol = str(args.get("symbol") or "")
            result = search_symbol(project_path, symbol)
            references = [
                EvidenceRef(path=item.path, reason=reason, source="search_symbol", start_line=item.line_number, end_line=item.line_number, excerpt=item.line)
                for item in result.matches
            ]
            return _tool_success(tool_name, symbol, f"Found {len(result.matches)} matches.", reason, references=references, related_files=[item.path for item in result.matches], warnings=result.warnings)
        if tool_name == "parse_dependencies":
            result = parse_dependencies(project_path)
            files = ["package.json", "pom.xml", "build.gradle", "build.gradle.kts", *[str(item) for item in result.get("java_config_files", [])]]
            return _tool_success(tool_name, "dependency files", "Parsed dependency metadata.", reason, related_files=files, notes=[_dependency_note(result)])
        if tool_name == "parse_routes":
            routes = parse_routes(project_path)
            return _tool_success(tool_name, "router files", f"Found {len(routes)} route candidates.", reason, related_files=[str(item.get("file") or "") for item in routes], notes=[f"路由候选: {', '.join(str(item.get('path')) for item in routes[:8])}"])
        if tool_name == "parse_api_calls":
            calls = parse_api_calls(project_path)
            return _tool_success(tool_name, "frontend API files", f"Found {len(calls)} frontend API calls.", reason, related_files=[str(item.get("file") or "") for item in calls], implementation_path=[str(item.get("file") or "") for item in calls])
        if tool_name == "parse_controller":
            endpoints = parse_controller(project_path)
            return _tool_success(tool_name, "Spring controllers", f"Found {len(endpoints)} controller endpoints.", reason, related_files=[str(item.get("backend_file") or "") for item in endpoints], implementation_path=[str(item.get("backend_file") or "") for item in endpoints])
        if tool_name == "parse_mapper":
            mappings = parse_mapper(project_path)
            return _tool_success(tool_name, "Mapper/Repository files", f"Found {len(mappings)} mapping candidates.", reason, related_files=[str(item.get("path") or "") for item in mappings], implementation_path=[str(item.get("path") or "") for item in mappings])
    except (ReadOnlyToolError, ValueError, OSError) as exc:
        return _tool_error(tool_name, str(args), str(exc), reason)
    return _tool_error(tool_name, str(args), f"Tool is not allowed: {tool_name}", reason)


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
) -> dict[str, Any]:
    return {
        "tool_call": ToolCallRecord(tool_name=tool_name, input_summary=input_summary, output_summary=output_summary, status="success", reason=reason),
        "references": references or [],
        "related_files": related_files or [],
        "implementation_path": implementation_path or [],
        "warnings": warnings or [],
        "notes": notes or [],
    }


def _tool_error(tool_name: str, input_summary: str, error: str, reason: str) -> dict[str, Any]:
    return {
        "tool_call": ToolCallRecord(tool_name=tool_name, input_summary=input_summary, output_summary=error, status="error", error=error, reason=reason),
        "warnings": [error],
    }


def _compose_answer(
    *,
    intent: AskIntent,
    question: str,
    memory: ProjectMemory,
    context: list[str],
    related_files: list[str],
    implementation_path: list[str],
    references: list[EvidenceRef],
) -> str:
    if intent == "project_overview":
        return f"{memory.project_name} 的当前理解是：{memory.project_memory.positioning}"
    if intent == "tech_stack":
        stack = "、".join(memory.project_memory.tech_stack) or "当前未识别明确技术栈"
        return f"这个项目识别到的主要技术栈是：{stack}。"
    if intent == "configuration":
        return "配置相关信息优先来自依赖和配置文件记忆；关键文件见相关文件列表。"
    if intent == "module_explanation":
        if context:
            return f"这个问题关联到这些模块/职责：{'；'.join(context[:4])}"
        return "当前项目记忆中没有找到明确模块证据。"
    if intent == "file_explanation":
        if related_files:
            return f"{related_files[0]} 是当前问题最相关的文件；回答基于文件记忆和已读取片段。"
        return "当前未能从文件记忆中定位到明确文件。"
    if intent == "api_usage":
        if implementation_path:
            return "这个接口的调用或实现候选链路见实现路径；Ask 模式已优先检索 API Index 并补充只读工具证据。"
        return "当前 API Index 和代码搜索中没有找到明确接口调用证据。"
    if intent == "call_chain":
        if implementation_path:
            return "当前只能给出候选实现链路，路径见实现路径列表；精准跨文件调用链仍需要后续增强。"
        return "当前代码中未找到明确流程证据。"
    return f"已围绕问题整理项目记忆和代码证据：{question}"


def _matched_modules(memory: ProjectMemory, question: str) -> list[ModuleMemorySummary]:
    lowered = question.lower()
    return [
        module
        for module in memory.module_summaries
        if module.name.lower() in lowered
        or module.responsibility.lower() in lowered
        or any(_stem(path).lower() in lowered for path in module.related_files)
    ][:5]


def _auth_modules(memory: ProjectMemory) -> list[ModuleMemorySummary]:
    keywords = ("auth", "login", "security", "permission", "user", "认证", "权限", "登录")
    return [
        module
        for module in memory.module_summaries
        if any(keyword in module.name.lower() or keyword in module.responsibility.lower() or any(keyword in path.lower() for path in module.related_files) for keyword in keywords)
    ][:5]


def _matched_files(memory: ProjectMemory, question: str) -> list[str]:
    lowered = question.lower()
    matched = [
        item.path
        for item in memory.file_summaries
        if item.path.lower() in lowered or _stem(item.path).lower() in lowered or item.path.split("/")[-1].lower() in lowered
    ]
    return matched[:8]


def _mentions_file(question: str, memory: ProjectMemory) -> bool:
    return bool(_matched_files(memory, question))


def _matched_api_entries(memory: ProjectMemory, question: str) -> list[ApiIndexEntry]:
    lowered = question.lower()
    return [entry for entry in memory.api_index if entry.path.lower() in lowered or (entry.backend_method and entry.backend_method.lower() in lowered)][:5]


def _previous_api_entries(memory: ProjectMemory, session_memory: SessionMemory | None) -> list[ApiIndexEntry]:
    if not session_memory or not session_memory.turns:
        return []
    previous = set(session_memory.turns[-1].referenced_apis)
    return [entry for entry in memory.api_index if entry.path in previous]


def _matched_flows(memory: ProjectMemory, question: str) -> list[FlowIndexEntry]:
    lowered = question.lower()
    return [flow for flow in memory.flow_index if flow.name.lower() in lowered or flow.kind.lower() in lowered][:5]


def _top_files(memory: ProjectMemory) -> list[str]:
    return [item.path for item in memory.file_summaries[:8]]


def _config_files(memory: ProjectMemory) -> list[str]:
    return [
        item.path
        for item in memory.file_summaries
        if item.role == "config" or item.path.endswith(("package.json", "pom.xml", "build.gradle", "build.gradle.kts", ".yml", ".yaml", ".properties"))
    ][:12]


def _files_by_paths(memory: ProjectMemory, paths: list[str]) -> list[Any]:
    wanted = set(paths)
    return [item for item in memory.file_summaries if item.path in wanted]


def _previous_files(session_memory: SessionMemory | None) -> list[str]:
    if not session_memory or not session_memory.turns:
        return []
    return session_memory.turns[-1].referenced_files


def _api_context(entry: ApiIndexEntry) -> str:
    parts = [entry.method or "UNKNOWN", entry.path]
    if entry.backend_file:
        parts.append(f"backend={entry.backend_file}")
    if entry.frontend_calls:
        parts.append(f"frontend={', '.join(entry.frontend_calls[:4])}")
    return " ".join(parts)


def _line_range(args: dict[str, Any]) -> tuple[int, int] | None:
    start = args.get("start_line")
    end = args.get("end_line")
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None


def _search_query(question: str) -> str:
    lowered = question.lower()
    for keyword in ("login", "auth", "token", "permission", "user", "登录", "认证", "权限", "接口"):
        if keyword in lowered:
            return keyword
    return question.strip()[:40] or "Controller"


def _dependency_note(result: dict[str, object]) -> str:
    frontend = result.get("frontend_dependencies")
    java = result.get("java_dependencies")
    return f"依赖摘要: frontend={len(frontend) if isinstance(frontend, dict) else 0}, java={len(java) if isinstance(java, dict) else 0}。"


def _notes_from_references(references: list[EvidenceRef]) -> list[str]:
    notes: list[str] = []
    for ref in references[:6]:
        location = f"{ref.path}:{ref.start_line}" if ref.start_line else ref.path
        notes.append(f"{location} 提供了当前回答的代码依据。")
    return notes


def _append_trace(state: AskState, stage: str, title: str, summary: str) -> list[TraceEvent]:
    events = list(state.get("trace_events", []))
    events.append(TraceEvent(index=len(events) + 1, stage=stage, title=title, summary=summary))
    return events


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
