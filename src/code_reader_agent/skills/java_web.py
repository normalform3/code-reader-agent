"""Java Web layering skill."""

from __future__ import annotations

from code_reader_agent.models import ModuleMemorySummary, PlannedToolCall, QueryHint, RepoMap, ResolvedQuery, SessionMemory, SkillScanResult
from code_reader_agent.skills.base import (
    DetectResult,
    file_summary,
    files_with_suffix,
    has_dependency,
    question_text,
    scan_file,
    symbol_item,
)


class JavaWebSkill:
    """Identify Java Web layered code structure."""

    name = "JavaWebSkill"
    description = "识别 Java Web Controller、Service、Mapper/Repository、Entity/DTO/VO 分层结构。"

    _suffix_roles = {
        "Controller.java": "controller",
        "Service.java": "service",
        "ServiceImpl.java": "service_impl",
        "Mapper.java": "mapper",
        "Repository.java": "repository",
        "Entity.java": "entity",
        "DTO.java": "dto",
        "VO.java": "vo",
        "Config.java": "config",
    }

    def detect(self, project: RepoMap) -> DetectResult:
        stack = {item.name for item in project.detected_stack}
        java_layer_files = self._layer_files(project)
        has_java_root = any(item.path.startswith("src/main/java/") for item in project.files)
        has_web_dependency = has_dependency(project, ("spring-web", "spring-boot-starter-web", "jakarta.servlet", "javax.servlet"))
        matched = has_java_root and (bool(java_layer_files) or has_web_dependency or "Java" in stack)
        confidence = 0.85 if java_layer_files else 0.62 if matched else 0.0
        reason = "存在 src/main/java 以及 Java Web 分层命名文件。" if java_layer_files else "存在 Java Web 目录或依赖线索。"
        return DetectResult(matched=matched, confidence=confidence, reason=reason if matched else "未发现 Java Web 分层证据。")

    def scan(self, project: RepoMap) -> SkillScanResult:
        layer_files = self._layer_files(project)
        files = [
            scan_file(item.path, self._role_for_path(item.path), "Java Web Skill 根据文件名识别分层角色。")
            for item in layer_files
        ]
        summaries = [
            file_summary(item.path, self._role_for_path(item.path), self._summary_for_role(self._role_for_path(item.path)))
            for item in layer_files
        ]
        symbols = [symbol_item(item.path, summary=self._summary_for_role(self._role_for_path(item.path))) for item in layer_files]
        modules = self._module_summaries(layer_files)
        return SkillScanResult(
            skill_name=self.name,
            files=files,
            file_summaries=summaries,
            module_summaries=modules,
            symbols=symbols,
            metadata={"layer_file_count": len(layer_files)},
        )

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        text = question_text(query)
        hints: list[QueryHint] = []
        if any(word in text for word in ("login", "登录", "认证", "auth", "token", "权限")):
            hints.extend(
                [
                    QueryHint(keyword="AuthService", reason="登录/认证通常落在 Java Web Service 层。", priority=90),
                    QueryHint(keyword="UserService", reason="登录功能通常需要用户服务。", priority=82),
                    QueryHint(keyword="UserMapper", reason="登录功能通常会查询用户表或用户实体。", priority=74),
                ]
            )
        if any(word in text for word in ("接口", "api", "controller")):
            hints.append(QueryHint(keyword="Controller", reason="Java Web 外部入口通常是 Controller。", priority=70))
        return hints

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        text = question_text(query)
        plans: list[PlannedToolCall] = []
        if any(word in text for word in ("login", "登录", "认证", "auth", "token", "权限")):
            for keyword in ("AuthService", "UserService", "UserMapper"):
                plans.append(
                    PlannedToolCall(
                        tool_name="search_keyword",
                        args={"keyword": keyword},
                        purpose=f"Java Web Skill 判断认证实现可能关联 {keyword}。",
                    )
                )
        return plans

    def get_answer_prompt(self) -> str:
        return "解释 Java Web 项目时，优先按照 Controller -> Service -> Mapper/Repository -> Entity 的分层结构说明。"

    def _layer_files(self, project: RepoMap) -> list[object]:
        suffixes = tuple(self._suffix_roles)
        return files_with_suffix(project, suffixes)

    def _role_for_path(self, path: str) -> str:
        for suffix, role in self._suffix_roles.items():
            if path.endswith(suffix):
                return role
        return "java_source"

    def _summary_for_role(self, role: str) -> str:
        return {
            "controller": "Java Web HTTP entrypoint candidate.",
            "service": "Java service/business boundary candidate.",
            "service_impl": "Java service implementation candidate.",
            "mapper": "Java Mapper data access candidate.",
            "repository": "Java Repository data access candidate.",
            "entity": "Java persistence entity candidate.",
            "dto": "Java request/response DTO candidate.",
            "vo": "Java view object candidate.",
            "config": "Java configuration candidate.",
        }.get(role, "Java source candidate.")

    def _module_summaries(self, layer_files: list[object]) -> list[ModuleMemorySummary]:
        grouped: dict[str, list[str]] = {}
        for item in layer_files:
            role = self._role_for_path(item.path)
            grouped.setdefault(role, []).append(item.path)
        summaries: list[ModuleMemorySummary] = []
        if not grouped:
            return summaries
        summaries.append(
            ModuleMemorySummary(
                name="Java Web Layering",
                responsibility="按 Controller、Service、Mapper/Repository、Entity/DTO/VO 组织 Java Web 阅读路径。",
                role="java_web",
                controller_files=grouped.get("controller", []),
                service_files=[*grouped.get("service", []), *grouped.get("service_impl", [])],
                related_files=[path for paths in grouped.values() for path in paths],
                related_entities=[*grouped.get("entity", []), *grouped.get("dto", []), *grouped.get("vo", [])],
            )
        )
        return summaries
