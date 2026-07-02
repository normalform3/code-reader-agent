"""Pydantic models for project scanning results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileTreeEntry(BaseModel):
    """A compact, UI-friendly project file tree entry."""

    path: str
    name: str
    kind: Literal["file", "directory"]
    depth: int


class PackageInfo(BaseModel):
    """Selected package.json fields used by the scanner."""

    found: bool
    name: str | None = None
    version: str | None = None
    package_manager: str | None = None
    scripts: dict[str, str] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    dev_dependencies: dict[str, str] = Field(default_factory=dict)


class JavaBuildInfo(BaseModel):
    """Selected Java build metadata used by the scanner."""

    found: bool
    build_tool: str | None = None
    group_id: str | None = None
    artifact_id: str | None = None
    version: str | None = None
    dependencies: dict[str, str | None] = Field(default_factory=dict)
    config_files: list[str] = Field(default_factory=list)


class StackTag(BaseModel):
    """A deterministic technology tag with a simple evidence pointer."""

    name: str
    source: str
    confidence: float = 1.0


class Entrypoint(BaseModel):
    """Known entrypoint file detected in the scanned project."""

    path: str
    kind: str
    exists: bool


class RepoMapEvidence(BaseModel):
    """Evidence collected while building a deterministic Repo Map."""

    id: str
    source: str
    path: str
    reason: str
    collected_by_tool: str


class RepoMapModule(BaseModel):
    """A module-like grouping that the UI and Agent can reason about."""

    id: str
    name: str
    type: str
    description: str
    responsibility: str
    key_files: list[str] = Field(default_factory=list)
    entry_files: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    evidence: list[str] = Field(default_factory=list)


class RepoMapFile(BaseModel):
    """A file entry enriched with a deterministic role and importance score."""

    path: str
    role: str
    language: str | None = None
    framework: str | None = None
    importance_score: float = 0.0
    summary: str = ""
    symbols: list[str] = Field(default_factory=list)
    related_modules: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RepoMap(BaseModel):
    """Structured project map used by the Web UI and future context manager."""

    project_name: str
    project_path: str
    detected_stack: list[StackTag]
    package_manager: str | None = None
    java_build_tool: str | None = None
    run_scripts: dict[str, str] = Field(default_factory=dict)
    entrypoints: list[Entrypoint] = Field(default_factory=list)
    modules: list[RepoMapModule] = Field(default_factory=list)
    files: list[RepoMapFile] = Field(default_factory=list)
    dependencies: dict[str, str | None] = Field(default_factory=dict)
    routes: list[str] = Field(default_factory=list)
    api_endpoints: list[str] = Field(default_factory=list)
    api_flows: list[str] = Field(default_factory=list)
    auth_flows: list[str] = Field(default_factory=list)
    stores: list[str] = Field(default_factory=list)
    java_packages: list[str] = Field(default_factory=list)
    controllers: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    repositories: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    evidence: list[RepoMapEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: str


class ProjectScanResult(BaseModel):
    """Structured scan output that can feed the future Repo Map builder."""

    project_name: str
    project_path: str
    file_tree: list[FileTreeEntry]
    package: PackageInfo
    java_build: JavaBuildInfo
    detected_stack: list[StackTag]
    entrypoints: list[Entrypoint]
    warnings: list[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    """A file-backed evidence pointer used by agent explanations."""

    path: str
    reason: str
    source: str


class PromptMessage(BaseModel):
    """A versioned prompt message ready to send to a future LLM provider."""

    role: Literal["system", "user"]
    content: str


class ProjectInterpretationRequest(BaseModel):
    """Input for the Phase 4 single-agent project interpretation flow."""

    project_path: str
    question: str = "这个项目是干什么的？我应该怎么运行，并从哪些文件开始看？"


class ReadingPathItem(BaseModel):
    """One recommended file or step in the onboarding reading path."""

    order: int
    path: str
    reason: str


class ProjectInterpretationResult(BaseModel):
    """Evidence-grounded single-agent project interpretation output."""

    project_name: str
    question: str
    skill: str
    prompt_version: str
    prompt_messages: list[PromptMessage]
    overview: str
    setup_summary: str
    reading_path: list[ReadingPathItem]
    evidence: list[EvidenceRef]
    warnings: list[str] = Field(default_factory=list)
