"""Vue frontend structure skill."""

from __future__ import annotations

from code_reader_agent.models import (
    FrontendApiCallIndexEntry,
    PlannedToolCall,
    QueryHint,
    RepoMap,
    ResolvedQuery,
    RouteIndexEntry,
    SessionMemory,
    SkillScanResult,
)
from code_reader_agent.skills.base import DetectResult, file_summary, question_text, scan_file, symbol_item
from code_reader_agent.tools.read_only import parse_api_calls, parse_routes


class VueSkill:
    """Identify Vue entrypoints, routes, pages, components, store, and API calls."""

    name = "VueSkill"
    description = "识别 Vue 前端项目结构、页面、路由、组件、状态和 API 请求。"

    def detect(self, project: RepoMap) -> DetectResult:
        stack = {item.name for item in project.detected_stack}
        vue_files = [item.path for item in project.files if item.path.endswith(".vue")]
        has_vue_dependency = "vue" in {name.lower() for name in project.dependencies}
        has_main = any(item.path in {"src/main.ts", "src/main.js"} for item in project.files)
        matched = bool(stack & {"Vue", "Vite", "Vue Router", "Pinia"}) or has_vue_dependency or bool(vue_files) or has_main
        confidence = 0.9 if stack & {"Vue", "Vite"} or has_vue_dependency else 0.72 if matched else 0.0
        reason = "检测到 Vue/Vite 依赖、入口文件或 .vue 文件。"
        return DetectResult(matched=matched, confidence=confidence, reason=reason if matched else "未发现 Vue 项目证据。")

    def scan(self, project: RepoMap) -> SkillScanResult:
        selected = self._selected_files(project)
        routes = self._routes(project.project_path)
        calls = self._frontend_calls(project.project_path)
        related_apis_by_file: dict[str, list[str]] = {}
        for call in calls:
            related_apis_by_file.setdefault(call.file, []).append(call.path)
        return SkillScanResult(
            skill_name=self.name,
            files=[
                scan_file(path, self._role(path), self._reason(path))
                for path in selected
            ],
            file_summaries=[
                file_summary(path, self._role(path), self._summary(path), related_apis_by_file.get(path, []))
                for path in selected
            ],
            symbols=[symbol_item(path, summary=self._summary(path)) for path in selected if path.endswith((".vue", ".ts", ".js"))],
            routes=routes,
            frontend_api_calls=calls,
            metadata={"route_count": len(routes), "frontend_api_call_count": len(calls)},
        )

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        text = question_text(query)
        hints: list[QueryHint] = []
        if any(word in text for word in ("login", "登录", "认证", "auth", "token", "权限")):
            hints.extend(
                [
                    QueryHint(keyword="Login.vue", reason="Vue 登录页面通常命名为 Login.vue。", priority=95),
                    QueryHint(keyword="auth.ts", reason="Vue 登录接口封装常见于 auth.ts。", priority=90),
                    QueryHint(keyword="src/api", reason="Vue API 请求通常集中在 src/api。", priority=84),
                    QueryHint(keyword="beforeEach", reason="Vue Router 登录守卫常见 beforeEach。", priority=80),
                ]
            )
        if any(word in text for word in ("页面", "路由", "router", "view", "component", "组件")):
            hints.extend(
                [
                    QueryHint(keyword="src/router", reason="Vue 页面入口优先看 router。", priority=82),
                    QueryHint(keyword="src/views", reason="Vue 路由页面通常位于 views。", priority=78),
                    QueryHint(keyword="src/components", reason="Vue 复用组件通常位于 components。", priority=70),
                ]
            )
        return hints

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        text = question_text(query)
        plans: list[PlannedToolCall] = []
        if any(word in text for word in ("页面", "路由", "router", "view", "登录", "login")):
            plans.append(
                PlannedToolCall(
                    tool_name="parse_routes",
                    args={},
                    purpose="Vue Skill 需要提取前端路由候选作为页面入口证据。",
                )
            )
        if any(word in text for word in ("接口", "api", "request", "axios", "fetch", "登录", "login")):
            plans.append(
                PlannedToolCall(
                    tool_name="parse_api_calls",
                    args={},
                    purpose="Vue Skill 需要提取前端 axios/fetch/request 调用候选。",
                )
            )
        if any(word in text for word in ("登录", "login", "认证", "auth")):
            for keyword in ("Login.vue", "auth.ts", "beforeEach"):
                plans.append(
                    PlannedToolCall(
                        tool_name="search_keyword",
                        args={"keyword": keyword},
                        purpose=f"Vue Skill 判断登录前端链路可能关联 {keyword}。",
                    )
                )
        return plans

    def get_answer_prompt(self) -> str:
        return "解释 Vue 项目时，优先按照 Router -> View -> Component -> Store/API 的结构说明。"

    def _selected_files(self, project: RepoMap) -> list[str]:
        selected: list[str] = []
        for item in project.files:
            path = item.path
            lowered = path.lower()
            if path in {"src/main.ts", "src/main.js", "src/App.vue"}:
                selected.append(path)
            elif any(part in lowered for part in ("/router/", "/views/", "/components/", "/api/", "/store/", "/stores/")):
                selected.append(path)
            elif path.endswith(".vue"):
                selected.append(path)
        return _dedupe_strings(selected)

    def _routes(self, project_path: str) -> list[RouteIndexEntry]:
        try:
            raw_routes = parse_routes(project_path)
        except Exception:
            return []
        return [
            RouteIndexEntry(
                path=str(item.get("path") or ""),
                file=str(item.get("file") or ""),
                line_number=item.get("line_number") if isinstance(item.get("line_number"), int) else None,
                description="Vue route candidate.",
            )
            for item in raw_routes
            if item.get("path") and item.get("file")
        ]

    def _frontend_calls(self, project_path: str) -> list[FrontendApiCallIndexEntry]:
        try:
            raw_calls = parse_api_calls(project_path)
        except Exception:
            return []
        return [
            FrontendApiCallIndexEntry(
                path=str(item.get("path") or ""),
                method=str(item.get("method") or "") or None,
                client=str(item.get("client") or "") or None,
                file=str(item.get("file") or ""),
                line_number=item.get("line_number") if isinstance(item.get("line_number"), int) else None,
            )
            for item in raw_calls
            if item.get("path") and item.get("file")
        ]

    def _role(self, path: str) -> str:
        lowered = path.lower()
        if path in {"src/main.ts", "src/main.js"}:
            return "vue_entrypoint"
        if "/router/" in lowered:
            return "router"
        if "/views/" in lowered or "/pages/" in lowered:
            return "view"
        if "/components/" in lowered:
            return "component"
        if "/api/" in lowered:
            return "api_client"
        if "/store/" in lowered or "/stores/" in lowered:
            return "store"
        if path.endswith(".vue"):
            return "component"
        return "frontend_source"

    def _reason(self, path: str) -> str:
        return "Vue Skill 根据入口、路由、页面、组件、状态或 API 目录识别该文件。"

    def _summary(self, path: str) -> str:
        return {
            "vue_entrypoint": "Vue application mount entrypoint candidate.",
            "router": "Vue Router definition candidate.",
            "view": "Vue routed page candidate.",
            "component": "Vue component candidate.",
            "api_client": "Vue frontend API/request wrapper candidate.",
            "store": "Vue state management candidate.",
        }.get(self._role(path), "Vue frontend source candidate.")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
