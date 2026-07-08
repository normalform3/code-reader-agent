"""Skill registry and Code Knowledge Index merge logic."""

from __future__ import annotations

from code_reader_agent.models import (
    ActiveSkillInfo,
    ApiIndexEntry,
    FlowIndexEntry,
    FrontendApiCallIndexEntry,
    IntentResult,
    PlannedToolCall,
    ProjectMemory,
    QueryHint,
    RepoMap,
    ResolvedQuery,
    RouteIndexEntry,
    RoutedSkillInfo,
    SessionMemory,
    SkillScanResult,
)
from code_reader_agent.skills.base import ActiveSkill, Skill
from code_reader_agent.skills.java_web import JavaWebSkill
from code_reader_agent.skills.mybatis import MyBatisSkill
from code_reader_agent.skills.rest_api import RestApiSkill
from code_reader_agent.skills.spring_boot import SpringBootSkill
from code_reader_agent.skills.vue import VueSkill


KNOWLEDGE_INDEX_VERSION = "skill-index-v1"


class SkillRegistry:
    """Register, detect, scan, and collect guidance from technology skills."""

    def __init__(self, skills: list[Skill] | None = None) -> None:
        self._skills: list[Skill] = []
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: Skill) -> None:
        """Register a skill by unique name."""

        if any(existing.name == skill.name for existing in self._skills):
            self._skills = [skill if existing.name == skill.name else existing for existing in self._skills]
            return
        self._skills.append(skill)

    def detect_active_skills(self, project: RepoMap) -> list[ActiveSkill]:
        """Detect active skills for a Repo Map."""

        active: list[ActiveSkill] = []
        for skill in self._skills:
            result = skill.detect(project)
            if result.matched:
                active.append(ActiveSkill(skill=skill, confidence=result.confidence, reason=result.reason))
        return sorted(active, key=lambda item: (-item.confidence, item.skill.name))

    def route_project_skills(self, project: RepoMap) -> list[ActiveSkill]:
        """Project-level skill routing for first scan and index building."""

        return self.detect_active_skills(project)

    def run_scan(self, project: RepoMap, active_skills: list[ActiveSkill] | None = None) -> list[SkillScanResult]:
        """Run active skills and return structured scan results."""

        active = active_skills if active_skills is not None else self.route_project_skills(project)
        return [item.skill.scan(project) for item in active]

    def apply_scan_results(
        self,
        memory: ProjectMemory,
        active_skills: list[ActiveSkill],
        scan_results: list[SkillScanResult],
    ) -> ProjectMemory:
        """Merge skill scan results into ProjectMemory's Code Knowledge Index."""

        active_infos = [item.to_info() for item in active_skills]
        overview = memory.project_memory.model_copy(
            update={
                "entry_points": _dedupe_strings(
                    [
                        *memory.project_memory.entry_points,
                        *[
                            str(path)
                            for result in scan_results
                            for path in result.metadata.get("entrypoints", [])
                            if isinstance(path, str)
                        ],
                    ]
                ),
                "config_files": _dedupe_strings(
                    [
                        *memory.project_memory.config_files,
                        *[
                            str(path)
                            for result in scan_results
                            for path in result.metadata.get("config_files", [])
                            if isinstance(path, str)
                        ],
                    ]
                ),
            }
        )
        api_index = _merge_api_entries(memory.api_index, [api for result in scan_results for api in result.apis])
        return memory.model_copy(
            update={
                "knowledge_index_version": KNOWLEDGE_INDEX_VERSION,
                "active_skills": active_infos,
                "project_memory": overview,
                "file_summaries": _dedupe_by_key(
                    [*memory.file_summaries, *[item for result in scan_results for item in result.file_summaries]],
                    lambda item: (item.path, item.role),
                ),
                "module_summaries": _dedupe_by_key(
                    [*memory.module_summaries, *[item for result in scan_results for item in result.module_summaries]],
                    lambda item: (item.name, item.role),
                ),
                "api_index": api_index,
                "flow_index": _dedupe_by_key(
                    [*memory.flow_index, *[item for result in scan_results for item in result.flows]],
                    lambda item: (item.name, item.kind),
                ),
                "symbol_index": _dedupe_by_key(
                    [*memory.symbol_index, *[item for result in scan_results for item in result.symbols]],
                    lambda item: (item.name, item.kind, item.file_path),
                )[:500],
                "route_index": _dedupe_route_entries([*memory.route_index, *[item for result in scan_results for item in result.routes]]),
                "frontend_api_call_index": _dedupe_frontend_calls(
                    [*memory.frontend_api_call_index, *[item for result in scan_results for item in result.frontend_api_calls]]
                ),
                "data_model_index": _dedupe_by_key(
                    [*memory.data_model_index, *[item for result in scan_results for item in result.data_models]],
                    lambda item: (item.name, item.kind, item.file, item.table or ""),
                ),
                "mapper_relations": _dedupe_by_key(
                    [*memory.mapper_relations, *[item for result in scan_results for item in result.mapper_relations]],
                    lambda item: (item.mapper_file, item.entity_file or "", item.table or ""),
                ),
            }
        )

    def build_indexes(self, project: RepoMap, memory: ProjectMemory) -> ProjectMemory:
        """Detect skills, scan, and return memory with skill indexes applied."""

        active = self.route_project_skills(project)
        scans = self.run_scan(project, active)
        return self.apply_scan_results(memory, active, scans)

    def route_query_skills(
        self,
        query: ResolvedQuery,
        intent_result: IntentResult,
        memory: ProjectMemory,
        session: SessionMemory,
    ) -> list[RoutedSkillInfo]:
        """Question-level skill routing from active skills to this Ask turn."""

        active_by_name = {item.name: item for item in memory.active_skills}
        routed: list[RoutedSkillInfo] = []
        for skill in self._skills:
            active = active_by_name.get(skill.name)
            if not active:
                continue
            score, signals = _score_skill_for_query(skill.name, active, query, intent_result, memory, session)
            if score < 0.52 and intent_result.intent != "tech_stack":
                continue
            routed.append(
                RoutedSkillInfo(
                    name=skill.name,
                    confidence=min(score, 0.99),
                    reason=_route_reason(skill.name, intent_result.intent, signals),
                    signals=signals[:8],
                )
            )
        return sorted(routed, key=lambda item: (-item.confidence, item.name))[:6]

    def collect_query_hints(self, query: ResolvedQuery, session: SessionMemory, active_infos: list[ActiveSkillInfo | RoutedSkillInfo]) -> list[QueryHint]:
        """Collect query hints from active skills."""

        active_names = {item.name for item in active_infos}
        hints: list[QueryHint] = []
        for skill in self._skills:
            if skill.name not in active_names:
                continue
            hints.extend(skill.get_query_hints(query, session))
        return _dedupe_by_key(hints, lambda item: item.keyword.lower())[:24]

    def collect_tool_plans(
        self,
        query: ResolvedQuery,
        context: list[str],
        active_infos: list[ActiveSkillInfo | RoutedSkillInfo],
    ) -> list[PlannedToolCall]:
        """Collect read-only tool plan suggestions from active skills."""

        active_names = {item.name for item in active_infos}
        plans: list[PlannedToolCall] = []
        for skill in self._skills:
            if skill.name not in active_names:
                continue
            plans.extend(skill.plan_tools(query, context))
        return _dedupe_tool_calls(plans)

    def collect_answer_prompts(self, active_infos: list[ActiveSkillInfo | RoutedSkillInfo]) -> list[str]:
        """Collect answer guidance from active skills."""

        active_names = {item.name for item in active_infos}
        prompts = [skill.get_answer_prompt() for skill in self._skills if skill.name in active_names]
        return _dedupe_strings(prompts)


def default_skill_registry() -> SkillRegistry:
    """Return the built-in MVP skill registry."""

    return SkillRegistry([JavaWebSkill(), SpringBootSkill(), MyBatisSkill(), VueSkill(), RestApiSkill()])


def _merge_api_entries(base_entries: list[ApiIndexEntry], additions: list[ApiIndexEntry]) -> list[ApiIndexEntry]:
    entries = [entry.model_copy(deep=True) for entry in base_entries]
    for addition in additions:
        matched = _find_api_entry(entries, addition)
        if matched:
            matched.frontend_calls = _dedupe_strings([*matched.frontend_calls, *addition.frontend_calls])
            matched.frontend_call_file = matched.frontend_call_file or addition.frontend_call_file
            matched.backend_file = matched.backend_file or addition.backend_file
            matched.backend_method = matched.backend_method or addition.backend_method
            matched.method = matched.method or addition.method
            matched.description = matched.description or addition.description
            continue
        entries.append(addition)
    return entries[:160]


def _find_api_entry(entries: list[ApiIndexEntry], candidate: ApiIndexEntry) -> ApiIndexEntry | None:
    normalized_candidate = candidate.path.strip("/")
    for entry in entries:
        normalized_entry = entry.path.strip("/")
        same_path = normalized_entry and normalized_candidate and (
            normalized_entry == normalized_candidate
            or normalized_entry.endswith(normalized_candidate)
            or normalized_candidate.endswith(normalized_entry)
        )
        same_backend = candidate.backend_file and entry.backend_file == candidate.backend_file and entry.backend_method == candidate.backend_method
        if same_path or same_backend:
            return entry
    return None


def _dedupe_route_entries(entries: list[RouteIndexEntry]) -> list[RouteIndexEntry]:
    return _dedupe_by_key(entries, lambda item: (item.path, item.file, item.line_number or 0))


def _dedupe_frontend_calls(entries: list[FrontendApiCallIndexEntry]) -> list[FrontendApiCallIndexEntry]:
    return _dedupe_by_key(entries, lambda item: (item.path, item.method or "", item.file, item.line_number or 0))


def _dedupe_tool_calls(calls: list[PlannedToolCall]) -> list[PlannedToolCall]:
    return _dedupe_by_key(calls, lambda item: (item.tool_name, tuple(sorted(item.args.items()))))


def _dedupe_by_key(values: list[object], key_fn: object) -> list[object]:
    seen: set[object] = set()
    unique: list[object] = []
    for value in values:
        key = key_fn(value)  # type: ignore[operator]
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _score_skill_for_query(
    skill_name: str,
    active: ActiveSkillInfo,
    query: ResolvedQuery,
    intent_result: IntentResult,
    memory: ProjectMemory,
    session: SessionMemory,
) -> tuple[float, list[str]]:
    text = " ".join(
        [
            query.resolved_question,
            " ".join(intent_result.keywords),
            " ".join(intent_result.possible_files),
            " ".join(intent_result.possible_apis),
            " ".join(intent_result.possible_symbols),
            " ".join(query.referenced_files),
            " ".join(query.referenced_apis),
            " ".join(query.referenced_flows),
            session.current_topic or "",
            session.focused_module or "",
            " ".join(session.focused_files),
            " ".join(session.focused_apis),
            " ".join(session.focused_flows),
        ]
    ).lower()
    score = active.confidence * 0.35
    signals = [f"project_active:{active.reason}"]

    def add(weight: float, signal: str) -> None:
        nonlocal score
        score += weight
        signals.append(signal)

    if intent_result.intent == "tech_stack":
        add(0.5, "tech_stack intent needs active stack skills")
    elif intent_result.intent == "project_overview":
        add(0.18, "project_overview can use active stack summary")

    if skill_name == "SpringBootSkill":
        if intent_result.intent in {"api_lookup", "flow_trace", "config_lookup"}:
            add(0.2, f"intent:{intent_result.intent}")
        if _contains_any(text, ("spring", "controller", "endpoint", "接口", "配置", "security", "jwt", "auth", "登录", "权限")):
            add(0.36, "question mentions Spring/API/security concepts")
        if _any_path(memory, ("controller.java", "security", "application.yml", "application.properties")):
            add(0.18, "index contains Spring Boot files")
    elif skill_name == "JavaWebSkill":
        if intent_result.intent in {"module_explanation", "file_explanation", "symbol_lookup", "flow_trace"}:
            add(0.2, f"intent:{intent_result.intent}")
        if _contains_any(text, ("java", "controller", "service", "mapper", "repository", "entity", "dto", "实现", "登录", "权限")):
            add(0.32, "question mentions Java Web layering")
        if _any_path(memory, ("controller.java", "service.java", "mapper.java", "repository.java", "entity.java")):
            add(0.16, "index contains Java layered files")
    elif skill_name == "MyBatisSkill":
        if intent_result.intent in {"config_lookup", "symbol_lookup", "flow_trace"}:
            add(0.18, f"intent:{intent_result.intent}")
        if _contains_any(text, ("mybatis", "mapper", "xml", "sql", "数据库", "表", "entity", "数据")):
            add(0.4, "question mentions mapper/data access concepts")
        if memory.data_model_index or memory.mapper_relations:
            add(0.22, "Code Knowledge Index has mapper/data model entries")
    elif skill_name == "VueSkill":
        if intent_result.intent in {"module_explanation", "file_explanation", "api_lookup", "flow_trace"}:
            add(0.2, f"intent:{intent_result.intent}")
        if _contains_any(text, ("vue", "页面", "路由", "router", "view", "component", "组件", "axios", "fetch", "login.vue", "auth.ts", "登录")):
            add(0.36, "question mentions Vue/frontend concepts")
        if memory.route_index or memory.frontend_api_call_index or _any_path(memory, (".vue", "src/router", "src/api")):
            add(0.18, "index contains Vue routes or frontend API calls")
    elif skill_name == "RestApiSkill":
        if intent_result.intent in {"api_lookup", "flow_trace"}:
            add(0.3, f"intent:{intent_result.intent}")
        if _contains_any(text, ("接口", "api", "endpoint", "调用", "request", "axios", "fetch", "/api", "登录")):
            add(0.34, "question mentions REST/API concepts")
        if intent_result.possible_apis or memory.api_index:
            add(0.2, "API Index has matching candidates")

    if query.referenced_files or query.referenced_apis or query.referenced_flows:
        add(0.08, "resolved query references session focus")
    return score, _dedupe_strings(signals)


def _route_reason(skill_name: str, intent: str, signals: list[str]) -> str:
    signal_text = "; ".join(signals[:3]) if signals else "active project skill"
    return f"{skill_name} selected for {intent}: {signal_text}."


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _any_path(memory: ProjectMemory, fragments: tuple[str, ...]) -> bool:
    paths = [
        *[item.path.lower() for item in memory.file_summaries],
        *[item.file_path.lower() for item in memory.symbol_index],
        *[item.backend_file.lower() for item in memory.api_index if item.backend_file],
        *[path.lower() for item in memory.api_index for path in item.frontend_calls],
        *[item.file.lower() for item in memory.route_index],
        *[item.file.lower() for item in memory.frontend_api_call_index],
        *[item.file.lower() for item in memory.data_model_index],
        *[item.mapper_file.lower() for item in memory.mapper_relations],
    ]
    return any(fragment in path for path in paths for fragment in fragments)
