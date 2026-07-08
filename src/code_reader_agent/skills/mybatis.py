"""MyBatis mapper and SQL mapping skill."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_reader_agent.models import (
    DataModelIndexEntry,
    MapperRelationEntry,
    PlannedToolCall,
    QueryHint,
    RepoMap,
    ResolvedQuery,
    SessionMemory,
    SkillScanResult,
)
from code_reader_agent.skills.base import DetectResult, file_summary, has_dependency, question_text, scan_file, symbol_item
from code_reader_agent.tools.read_only import ReadOnlyToolError, parse_mapper, read_file


class MyBatisSkill:
    """Identify MyBatis Mapper, XML, SQL, and entity mapping candidates."""

    name = "MyBatisSkill"
    description = "识别 Mapper、XML、SQL 片段和实体/表映射候选。"

    def detect(self, project: RepoMap) -> DetectResult:
        stack = {item.name for item in project.detected_stack}
        mapper_files = self._mapper_files(project)
        matched = "MyBatis" in stack or has_dependency(project, ("mybatis", "mybatis-plus")) or bool(mapper_files)
        confidence = 0.9 if "MyBatis" in stack or has_dependency(project, ("mybatis", "mybatis-plus")) else 0.7 if mapper_files else 0.0
        reason = "检测到 MyBatis 依赖、技术栈标签、Mapper 接口或 Mapper XML。"
        return DetectResult(matched=matched, confidence=confidence, reason=reason if matched else "未发现 MyBatis 证据。")

    def scan(self, project: RepoMap) -> SkillScanResult:
        mapper_records = self._parse_mapper(project.project_path)
        mapper_paths = _dedupe_strings([str(item.get("path") or "") for item in mapper_records])
        if not mapper_paths:
            mapper_paths = [item.path for item in self._mapper_files(project)]
        data_models = [model for path in mapper_paths for model in self._data_models(project, path)]
        relations = [relation for path in mapper_paths for relation in self._relations(project, path, data_models)]
        return SkillScanResult(
            skill_name=self.name,
            files=[
                scan_file(path, self._role(path), "MyBatis Skill 识别到 Mapper/Repository/XML 或数据访问候选。")
                for path in mapper_paths
            ],
            file_summaries=[
                file_summary(path, self._role(path), "MyBatis mapper, repository, SQL, or XML mapping candidate.")
                for path in mapper_paths
            ],
            symbols=[symbol_item(path, summary="MyBatis mapper or XML mapping candidate.") for path in mapper_paths if path.endswith(".java")],
            data_models=data_models,
            mapper_relations=relations,
            metadata={"mapper_count": len(mapper_paths)},
        )

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        text = question_text(query)
        hints: list[QueryHint] = []
        if any(word in text for word in ("mapper", "mybatis", "sql", "数据", "表", "数据库", "查询")):
            hints.extend(
                [
                    QueryHint(keyword="Mapper", reason="MyBatis 数据访问通常从 Mapper 接口或 XML 开始。", priority=82),
                    QueryHint(keyword="<select", reason="MyBatis XML 查询语句候选。", priority=76),
                    QueryHint(keyword="@Select", reason="MyBatis 注解 SQL 查询候选。", priority=74),
                ]
            )
        if any(word in text for word in ("login", "登录", "用户", "user")):
            hints.append(QueryHint(keyword="UserMapper", reason="登录通常会通过用户 Mapper 查询用户数据。", priority=80))
        return hints

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        text = question_text(query)
        if any(word in text for word in ("mapper", "mybatis", "sql", "数据", "表", "数据库", "查询", "登录", "login")):
            return [
                PlannedToolCall(
                    tool_name="parse_mapper",
                    args={},
                    purpose="MyBatis Skill 需要提取 Mapper、Repository 和 XML 映射候选。",
                )
            ]
        return []

    def get_answer_prompt(self) -> str:
        return "解释 MyBatis 相关问题时，需要指出 Mapper 接口、Mapper XML、SQL、实体类和可能的数据表。"

    def _mapper_files(self, project: RepoMap) -> list[object]:
        return [
            item
            for item in project.files
            if item.path.endswith(("Mapper.java", "Repository.java", "Dao.java", "Mapper.xml"))
            or "/mapper/" in item.path.lower()
            or "/repository/" in item.path.lower()
        ]

    def _parse_mapper(self, project_path: str) -> list[dict[str, object]]:
        try:
            return parse_mapper(project_path)
        except Exception:
            return []

    def _role(self, path: str) -> str:
        if path.endswith("Mapper.xml"):
            return "mapper_xml"
        if path.endswith("Mapper.java"):
            return "mapper"
        if path.endswith(("Repository.java", "Dao.java")):
            return "repository"
        return "data_access"

    def _data_models(self, project: RepoMap, path: str) -> list[DataModelIndexEntry]:
        content = self._read(project, path)
        if not content:
            return []
        models: list[DataModelIndexEntry] = []
        sql_patterns = [
            r"@(Select|Insert|Update|Delete)\s*\(\s*\"([^\"]+)\"",
            r"<(select|insert|update|delete)\b[^>]*>(.*?)</\1>",
        ]
        for pattern in sql_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
                sql = " ".join(match.group(match.lastindex or 1).split())
                table = _table_from_sql(sql)
                models.append(
                    DataModelIndexEntry(
                        name=PurePosixPath(path).stem,
                        kind="sql",
                        file=path,
                        table=table,
                        sql=sql[:500],
                        summary="MyBatis SQL candidate.",
                    )
                )
        if not models and path.endswith((".java", ".xml")):
            models.append(
                DataModelIndexEntry(
                    name=PurePosixPath(path).stem,
                    kind=self._role(path),
                    file=path,
                    summary="MyBatis mapping candidate.",
                )
            )
        return models

    def _relations(self, project: RepoMap, path: str, models: list[DataModelIndexEntry]) -> list[MapperRelationEntry]:
        stem = PurePosixPath(path).stem.replace("Mapper", "").replace("Repository", "").replace("Dao", "")
        entity = next((item.path for item in project.files if item.path.endswith(f"{stem}Entity.java") or item.path.endswith(f"{stem}.java")), None)
        tables = _dedupe_strings([model.table or "" for model in models if model.file == path])
        if entity or tables:
            return [
                MapperRelationEntry(
                    mapper_file=path,
                    entity_file=entity,
                    table=tables[0] if tables else None,
                    reason="MyBatis Skill 根据 Mapper 命名、实体命名和 SQL 表名建立候选关系。",
                )
            ]
        return []

    def _read(self, project: RepoMap, path: str) -> str:
        try:
            return read_file(project.project_path, path, line_range=(1, 260)).content
        except (ReadOnlyToolError, ValueError, OSError):
            return ""


def _table_from_sql(sql: str) -> str | None:
    match = re.search(r"\b(?:from|into|update)\s+([A-Za-z0-9_.$`]+)", sql, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip("`")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
