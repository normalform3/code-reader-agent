"""Base interfaces and helpers for technology-specific CodeReader skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from pydantic import BaseModel

from code_reader_agent.models import (
    ActiveSkillInfo,
    FileMemorySummary,
    PlannedToolCall,
    QueryHint,
    RepoMap,
    RepoMapFile,
    ResolvedQuery,
    SessionMemory,
    SkillScanFile,
    SkillScanResult,
    SymbolIndexItem,
)


class DetectResult(BaseModel):
    """Result of checking whether a skill applies to a project."""

    matched: bool
    confidence: float = 0.0
    reason: str = ""


class Skill(Protocol):
    """Technology-stack plugin for scan, indexing, retrieval, and answer guidance."""

    name: str
    description: str

    def detect(self, project: RepoMap) -> DetectResult:
        """Return whether this skill should be active for the project."""

    def scan(self, project: RepoMap) -> SkillScanResult:
        """Scan project metadata and read-only parser outputs into structured indexes."""

    def get_query_hints(self, query: ResolvedQuery, session: SessionMemory) -> list[QueryHint]:
        """Return retrieval hints for an Ask query."""

    def plan_tools(self, query: ResolvedQuery, retrieved_context: list[str]) -> list[PlannedToolCall]:
        """Return read-only tool suggestions for an Ask query."""

    def get_answer_prompt(self) -> str:
        """Return technology-specific answer style guidance."""


@dataclass(frozen=True)
class ActiveSkill:
    """A concrete active skill plus its detection metadata."""

    skill: Skill
    confidence: float
    reason: str

    def to_info(self) -> ActiveSkillInfo:
        """Convert to the public API model."""

        return ActiveSkillInfo(name=self.skill.name, confidence=self.confidence, reason=self.reason)


def scan_file(path: str, role: str, reason: str) -> SkillScanFile:
    """Build a scan file record."""

    return SkillScanFile(path=path, role=role, reason=reason)


def file_summary(path: str, role: str, responsibility: str, related_apis: list[str] | None = None) -> FileMemorySummary:
    """Build a compact file summary contributed by a skill."""

    return FileMemorySummary(
        path=path,
        responsibility=responsibility,
        role=role,
        language=language_for_path(path),
        symbols=fallback_symbols(path),
        related_apis=related_apis or [],
        hash=f"skill:{path}:{role}",
    )


def symbol_item(path: str, kind: str | None = None, summary: str | None = None) -> SymbolIndexItem:
    """Build a conservative symbol index item from a file path."""

    name = PurePosixPath(path).stem
    inferred = kind or symbol_kind(path, name)
    return SymbolIndexItem(name=name, kind=inferred, file_path=path, summary=summary)


def files_with_suffix(project: RepoMap, suffixes: tuple[str, ...]) -> list[RepoMapFile]:
    """Return repo files with matching suffixes."""

    return [item for item in project.files if item.path.endswith(suffixes)]


def files_containing(project: RepoMap, fragments: tuple[str, ...]) -> list[RepoMapFile]:
    """Return repo files whose lowercase path contains any fragment."""

    return [item for item in project.files if any(fragment in item.path.lower() for fragment in fragments)]


def has_dependency(project: RepoMap, fragments: tuple[str, ...]) -> bool:
    """Return whether any dependency name contains one of the fragments."""

    names = [name.lower() for name in project.dependencies]
    return any(fragment in name for name in names for fragment in fragments)


def question_text(query: ResolvedQuery) -> str:
    """Return lowercased resolved Ask text."""

    return query.resolved_question.lower()


def fallback_symbols(path: str) -> list[str]:
    """Return a conservative one-symbol fallback for source files."""

    stem = PurePosixPath(path).stem
    if path.endswith((".java", ".vue", ".ts", ".tsx", ".js", ".jsx", ".xml")) and stem:
        return [stem]
    return []


def language_for_path(path: str) -> str:
    """Infer language from path suffix."""

    suffix = PurePosixPath(path).suffix
    return {
        ".java": "Java",
        ".vue": "Vue",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".xml": "XML",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".properties": "Properties",
    }.get(suffix, "")


def symbol_kind(path: str, name: str) -> str:
    """Infer symbol kind accepted by the public SymbolIndexItem model."""

    if path.endswith(".vue"):
        return "component"
    if path.endswith(".java"):
        return "class" if name[:1].isupper() else "method"
    if path.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "function"
    return "class" if name[:1].isupper() else "function"
