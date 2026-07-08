"""REST API mapping skill."""

from __future__ import annotations

from code_reader_agent.models import (
    ApiIndexEntry,
    FlowIndexEntry,
    FrontendApiCallIndexEntry,
    PlannedToolCall,
    QueryHint,
    RepoMap,
    ResolvedQuery,
    SessionMemory,
    SkillScanResult,
)
from code_reader_agent.skills.base import DetectResult, question_text
from code_reader_agent.tools.read_only import parse_api_calls, parse_controller


class RestApiSkill:
    """Map backend Controller endpoints and frontend HTTP calls."""

    name = "RestApiSkill"
    description = "识别 REST 接口、前端调用和前后端接口映射候选。"

    def detect(self, project: RepoMap) -> DetectResult:
        has_backend = bool(project.controllers) or any(item.path.endswith("Controller.java") for item in project.files)
        has_frontend = any(
            item.role == "api_client" or "/api/" in item.path.lower() or item.path.endswith((".vue", ".ts", ".js"))
            for item in project.files
        )
        has_api_candidates = bool(project.api_endpoints or project.api_flows)
        matched = has_api_candidates or has_backend or has_frontend
        confidence = 0.82 if has_backend and has_frontend else 0.68 if matched else 0.0
        reason = "检测到 Controller 接口或前端 axios/fetch/request 调用候选。"
        return DetectResult(matched=matched, confidence=confidence, reason=reason if matched else "未发现 REST API 证据。")

    def scan(self, project: RepoMap) -> SkillScanResult:
        backend_entries = self._backend_entries(project.project_path)
        frontend_calls = self._frontend_calls(project.project_path)
        apis = self._merge_api_index(backend_entries, frontend_calls)
        flows = self._flow_candidates(apis)
        return SkillScanResult(
            skill_name=self.name,
            apis=apis,
            frontend_api_calls=frontend_calls,
            flows=flows,
            metadata={"backend_api_count": len(backend_entries), "frontend_api_call_count": len(frontend_calls)},
        )

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        text = question_text(query)
        hints: list[QueryHint] = []
        if any(word in text for word in ("接口", "api", "endpoint", "调用", "request", "axios", "fetch")):
            hints.extend(
                [
                    QueryHint(keyword="@RequestMapping", reason="REST API 后端路径常见于 Spring mapping 注解。", priority=82),
                    QueryHint(keyword="axios", reason="REST API 前端调用常见 axios。", priority=78),
                    QueryHint(keyword="fetch", reason="REST API 前端调用也可能使用 fetch。", priority=74),
                    QueryHint(keyword="request(", reason="REST API 前端调用可能封装为 request。", priority=72),
                ]
            )
        if any(word in text for word in ("登录", "login", "auth")):
            hints.extend(
                [
                    QueryHint(keyword="/login", reason="登录接口路径常见 /login。", priority=86),
                    QueryHint(keyword="/auth", reason="认证接口路径常见 /auth。", priority=80),
                ]
            )
        return hints

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        text = question_text(query)
        if any(word in text for word in ("接口", "api", "endpoint", "调用", "request", "axios", "fetch", "登录", "login", "auth")):
            return [
                PlannedToolCall(
                    tool_name="parse_api_calls",
                    args={},
                    purpose="REST API Skill 需要提取前端接口调用候选。",
                ),
                PlannedToolCall(
                    tool_name="parse_controller",
                    args={},
                    purpose="REST API Skill 需要提取后端 Controller 接口候选。",
                ),
            ]
        return []

    def get_answer_prompt(self) -> str:
        return "解释接口问题时，需要说明 HTTP 方法、接口路径、后端处理方法、前端调用位置。"

    def _backend_entries(self, project_path: str) -> list[ApiIndexEntry]:
        try:
            endpoints = parse_controller(project_path)
        except Exception:
            return []
        entries: list[ApiIndexEntry] = []
        for endpoint in endpoints:
            path = str(endpoint.get("path") or "")
            backend_file = str(endpoint.get("backend_file") or "")
            if not path and not backend_file:
                continue
            entries.append(
                ApiIndexEntry(
                    path=path or backend_file,
                    method=str(endpoint.get("method") or "") or None,
                    backend_method=str(endpoint.get("backend_method") or "") or None,
                    backend_file=backend_file or None,
                    description="REST backend endpoint candidate.",
                )
            )
        return entries

    def _frontend_calls(self, project_path: str) -> list[FrontendApiCallIndexEntry]:
        try:
            calls = parse_api_calls(project_path)
        except Exception:
            return []
        return [
            FrontendApiCallIndexEntry(
                path=str(call.get("path") or ""),
                method=str(call.get("method") or "") or None,
                client=str(call.get("client") or "") or None,
                file=str(call.get("file") or ""),
                line_number=call.get("line_number") if isinstance(call.get("line_number"), int) else None,
            )
            for call in calls
            if call.get("path") and call.get("file")
        ]

    def _merge_api_index(
        self,
        backend_entries: list[ApiIndexEntry],
        frontend_calls: list[FrontendApiCallIndexEntry],
    ) -> list[ApiIndexEntry]:
        entries = [entry.model_copy(deep=True) for entry in backend_entries]
        for call in frontend_calls:
            matched = _find_api_entry(entries, call.path)
            if matched:
                matched.frontend_calls = _dedupe_strings([*matched.frontend_calls, call.file])
                matched.frontend_call_file = matched.frontend_call_file or call.file
                if not matched.method and call.method:
                    matched.method = call.method
                continue
            entries.append(
                ApiIndexEntry(
                    path=call.path,
                    method=call.method,
                    frontend_call_file=call.file,
                    frontend_calls=[call.file],
                    description="REST frontend API call candidate.",
                )
            )
        return entries

    def _flow_candidates(self, apis: list[ApiIndexEntry]) -> list[FlowIndexEntry]:
        flows: list[FlowIndexEntry] = []
        for entry in apis[:30]:
            steps = _dedupe_strings([*entry.frontend_calls, entry.backend_file or ""])
            if len(steps) < 2:
                continue
            flows.append(
                FlowIndexEntry(
                    name=f"{entry.method or 'UNKNOWN'} {entry.path}",
                    kind="api",
                    description="REST API Skill 关联出的前端调用到后端处理候选。",
                    steps=steps,
                    evidence_files=steps,
                    confidence=0.58,
                )
            )
        return flows


def _find_api_entry(entries: list[ApiIndexEntry], path: str) -> ApiIndexEntry | None:
    normalized_call = path.strip("/")
    for entry in entries:
        normalized_entry = entry.path.strip("/")
        if not normalized_entry:
            continue
        if normalized_entry == normalized_call or normalized_entry.endswith(normalized_call) or normalized_call.endswith(normalized_entry):
            return entry
    return None


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
