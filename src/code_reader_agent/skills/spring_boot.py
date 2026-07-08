"""Spring Boot skill for application entrypoints, config, controllers, and security."""

from __future__ import annotations

from code_reader_agent.models import (
    ApiIndexEntry,
    PlannedToolCall,
    QueryHint,
    RepoMap,
    ResolvedQuery,
    SessionMemory,
    SkillScanResult,
)
from code_reader_agent.skills.base import DetectResult, file_summary, has_dependency, question_text, scan_file, symbol_item
from code_reader_agent.tools.read_only import ReadOnlyToolError, parse_controller, read_file


class SpringBootSkill:
    """Identify Spring Boot runtime and HTTP API structure."""

    name = "SpringBootSkill"
    description = "识别 Spring Boot 启动类、配置文件、Controller 接口和安全配置。"

    def detect(self, project: RepoMap) -> DetectResult:
        stack = {item.name for item in project.detected_stack}
        has_spring_stack = bool(stack & {"Spring Boot", "Spring Web", "Spring Security"})
        has_dependency_match = has_dependency(project, ("spring-boot",))
        has_application = any(item.path.endswith("Application.java") for item in project.files)
        matched = has_spring_stack or has_dependency_match or has_application
        confidence = 0.9 if has_spring_stack or has_dependency_match else 0.68 if matched else 0.0
        reason = "检测到 Spring Boot 依赖、技术栈标签或 Application 启动类。"
        return DetectResult(matched=matched, confidence=confidence, reason=reason if matched else "未发现 Spring Boot 证据。")

    def scan(self, project: RepoMap) -> SkillScanResult:
        entrypoints = [item.path for item in project.files if item.path.endswith("Application.java") or self._file_contains(project, item.path, "@SpringBootApplication")]
        config_files = [
            item.path
            for item in project.files
            if item.path.endswith(("application.yml", "application.yaml", "application.properties"))
        ]
        controller_files = [
            item.path
            for item in project.files
            if item.path.endswith("Controller.java") or self._file_contains(project, item.path, "@RestController") or self._file_contains(project, item.path, "@Controller")
        ]
        security_files = [
            item.path
            for item in project.files
            if any(token in item.path.lower() for token in ("security", "jwt", "userdetailsservice"))
            or self._file_contains(project, item.path, "SecurityFilterChain")
            or self._file_contains(project, item.path, "UserDetailsService")
        ]
        selected = _dedupe_strings([*entrypoints, *config_files, *controller_files, *security_files])
        apis = self._api_index(project.project_path)
        return SkillScanResult(
            skill_name=self.name,
            files=[
                scan_file(path, self._role(path), self._reason(path))
                for path in selected
            ],
            file_summaries=[
                file_summary(path, self._role(path), self._summary(path), [api.path for api in apis if api.backend_file == path])
                for path in selected
            ],
            symbols=[symbol_item(path, summary=self._summary(path)) for path in selected if path.endswith(".java")],
            apis=apis,
            metadata={
                "entrypoints": entrypoints,
                "config_files": config_files,
                "security_files": security_files,
            },
        )

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        text = question_text(query)
        hints: list[QueryHint] = []
        if any(word in text for word in ("login", "登录", "认证", "auth", "token", "权限")):
            hints.extend(
                [
                    QueryHint(keyword="AuthController", reason="Spring Boot 登录入口常见于 AuthController。", priority=96),
                    QueryHint(keyword="LoginController", reason="Spring Boot 登录入口也可能命名为 LoginController。", priority=94),
                    QueryHint(keyword="SecurityConfig", reason="认证/鉴权通常需要检查 Spring Security 配置。", priority=92),
                    QueryHint(keyword="SecurityFilterChain", reason="Spring Security 过滤链决定请求鉴权方式。", priority=88),
                    QueryHint(keyword="Jwt", reason="登录 token 流程常见 JWT 相关过滤器或工具。", priority=84),
                    QueryHint(keyword="UserDetailsService", reason="Spring Security 登录通常会加载用户详情。", priority=80),
                ]
            )
        if any(word in text for word in ("接口", "api", "endpoint", "controller")):
            hints.extend(
                [
                    QueryHint(keyword="@RequestMapping", reason="Spring Controller 类或方法路径。", priority=76),
                    QueryHint(keyword="@GetMapping", reason="Spring GET 接口路径。", priority=72),
                    QueryHint(keyword="@PostMapping", reason="Spring POST 接口路径。", priority=72),
                ]
            )
        return hints

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        text = question_text(query)
        plans: list[PlannedToolCall] = []
        if any(word in text for word in ("接口", "api", "endpoint", "controller", "登录", "login", "认证", "auth")):
            plans.append(
                PlannedToolCall(
                    tool_name="parse_controller",
                    args={},
                    purpose="Spring Boot Skill 需要提取 Controller 接口候选作为真实代码证据。",
                    priority=82,
                )
            )
        if any(word in text for word in ("登录", "login", "认证", "auth", "token", "权限")):
            priorities = {
                "AuthController": 79,
                "SecurityConfig": 78,
                "SecurityFilterChain": 76,
                "Jwt": 74,
                "UserDetailsService": 72,
            }
            for keyword in ("AuthController", "SecurityConfig", "SecurityFilterChain", "Jwt", "UserDetailsService"):
                plans.append(
                    PlannedToolCall(
                        tool_name="search_keyword",
                        args={"keyword": keyword},
                        purpose=f"Spring Boot Skill 判断认证链路可能关联 {keyword}。",
                        priority=priorities[keyword],
                    )
                )
        return plans

    def get_answer_prompt(self) -> str:
        return "解释 Spring Boot 项目时，需要说明启动类、配置文件、接口路径、Controller 方法和相关 Service。"

    def _api_index(self, project_path: str) -> list[ApiIndexEntry]:
        entries: list[ApiIndexEntry] = []
        try:
            endpoints = parse_controller(project_path)
        except Exception:
            return entries
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
                    description="Spring Boot Controller endpoint candidate.",
                )
            )
        return entries

    def _file_contains(self, project: RepoMap, path: str, keyword: str) -> bool:
        if not path.endswith((".java", ".yml", ".yaml", ".properties")):
            return False
        try:
            return keyword in read_file(project.project_path, path, line_range=(1, 220)).content
        except (ReadOnlyToolError, ValueError, OSError):
            return False

    def _role(self, path: str) -> str:
        lowered = path.lower()
        if path.endswith("Application.java"):
            return "spring_boot_entrypoint"
        if path.endswith(("application.yml", "application.yaml", "application.properties")):
            return "spring_config"
        if path.endswith("Controller.java"):
            return "controller"
        if any(token in lowered for token in ("security", "jwt", "userdetailsservice")):
            return "security"
        return "spring_source"

    def _reason(self, path: str) -> str:
        return {
            "spring_boot_entrypoint": "Spring Boot Skill 识别到启动类候选。",
            "spring_config": "Spring Boot Skill 识别到应用配置文件。",
            "controller": "Spring Boot Skill 识别到 Controller 接口入口。",
            "security": "Spring Boot Skill 识别到安全/认证配置候选。",
        }.get(self._role(path), "Spring Boot Skill 识别到框架相关源码。")

    def _summary(self, path: str) -> str:
        return {
            "spring_boot_entrypoint": "Spring Boot application entrypoint candidate.",
            "spring_config": "Spring Boot runtime configuration candidate.",
            "controller": "Spring MVC Controller endpoint candidate.",
            "security": "Spring Security, JWT, or user-details candidate.",
        }.get(self._role(path), "Spring Boot source candidate.")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
