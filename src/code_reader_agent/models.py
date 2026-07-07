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


class ProjectSummary(BaseModel):
    """First-screen explanation of what the repository appears to do."""

    one_liner: str
    audience: str
    problem: str
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list)


class StackExplanation(BaseModel):
    """A technology tag explained in terms of its likely project role."""

    name: str
    category: str
    purpose: str
    evidence_source: str
    confidence: float = 1.0


class DirectoryInsight(BaseModel):
    """A directory-level reading hint for the overview page."""

    path: str
    role: str
    importance: Literal["core", "supporting", "skippable"]
    reason: str


class ReadingRecommendation(BaseModel):
    """A first-pass recommendation for what to read or skip."""

    path: str
    action: Literal["read_first", "skip_for_now"]
    reason: str
    priority: int


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
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str | None = None
    collected_at: str | None = None


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
    reading_priority: int = 99
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
    project_summary: ProjectSummary | None = None
    detected_stack: list[StackTag]
    stack_explanations: list[StackExplanation] = Field(default_factory=list)
    directory_insights: list[DirectoryInsight] = Field(default_factory=list)
    reading_recommendations: list[ReadingRecommendation] = Field(default_factory=list)
    package_manager: str | None = None
    java_build_tool: str | None = None
    run_scripts: dict[str, str] = Field(default_factory=dict)
    entrypoints: list[Entrypoint] = Field(default_factory=list)
    modules: list[RepoMapModule] = Field(default_factory=list)
    files: list[RepoMapFile] = Field(default_factory=list)
    file_tree: list[FileTreeEntry] = Field(default_factory=list)
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


class GitHubImportRequest(BaseModel):
    """Input for importing a public GitHub repository into the local cache."""

    github_url: str


class GitHubImportResult(BaseModel):
    """Result from importing a public GitHub repository for read-only analysis."""

    project_name: str
    project_path: str
    github_url: str
    repository: str
    reused_cache: bool
    warnings: list[str] = Field(default_factory=list)


class ProjectSession(BaseModel):
    """A local project analysis session shown in the left sidebar."""

    id: str
    title: str
    project_name: str
    project_path: str
    github_url: str | None = None
    repository: str | None = None
    status: str = "ready"
    last_question: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class ProjectSessionCreate(BaseModel):
    """Input for creating or refreshing a local project session."""

    project_name: str
    project_path: str
    title: str | None = None
    github_url: str | None = None
    repository: str | None = None
    status: str = "ready"
    last_question: str | None = None
    last_error: str | None = None


class ProjectSessionUpdate(BaseModel):
    """Patchable fields for a local project session."""

    title: str | None = None
    status: str | None = None
    last_question: str | None = None
    last_error: str | None = None


class RegistryItemCreate(BaseModel):
    """Input for creating a custom tool or skill registry item."""

    name: str
    description: str = ""
    notes: str = ""
    details: list["RegistryDetailSection"] = Field(default_factory=list)
    enabled: bool = True


class RegistryItemUpdate(BaseModel):
    """Patchable fields for tool and skill registry items."""

    name: str | None = None
    description: str | None = None
    notes: str | None = None
    details: list["RegistryDetailSection"] | None = None
    enabled: bool | None = None


class RegistryDetailSection(BaseModel):
    """Structured detail content for a tool or skill registry item."""

    title: str
    items: list[str] = Field(default_factory=list)


class RegistryTool(BaseModel):
    """A tool definition visible in the local management page."""

    id: str
    name: str
    description: str = ""
    notes: str = ""
    details: list[RegistryDetailSection] = Field(default_factory=list)
    enabled: bool = True
    builtin: bool = False
    created_at: str
    updated_at: str


class RegistrySkill(BaseModel):
    """A skill definition visible in the local management page."""

    id: str
    name: str
    description: str = ""
    notes: str = ""
    details: list[RegistryDetailSection] = Field(default_factory=list)
    enabled: bool = True
    builtin: bool = False
    created_at: str
    updated_at: str


class EvidenceRef(BaseModel):
    """A file-backed evidence pointer used by agent explanations."""

    path: str
    reason: str
    source: str
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str | None = None


class ToolCallRecord(BaseModel):
    """A compact record of a deterministic tool action shown in the UI."""

    tool_name: str
    input_summary: str
    output_summary: str
    status: Literal["success", "error"]
    error: str | None = None
    reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReadFileResult(BaseModel):
    """Result from the safe read-only file tool."""

    path: str
    content: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class SearchCodeMatch(BaseModel):
    """One search result from the safe code search tool."""

    path: str
    line_number: int
    line: str


class SearchCodeResult(BaseModel):
    """Result from the safe code search tool."""

    query: str
    matches: list[SearchCodeMatch] = Field(default_factory=list)
    used_backend: str
    warnings: list[str] = Field(default_factory=list)


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


class ProjectManualModule(BaseModel):
    """Module explanation in the reusable first-pass project manual."""

    id: str
    name: str
    type: str
    responsibility: str
    key_files: list[str] = Field(default_factory=list)
    entry_files: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class ProjectManualEntrypoint(BaseModel):
    """Entrypoint explanation in the reusable first-pass project manual."""

    path: str
    kind: str
    reason: str


class ProjectManualDirectory(BaseModel):
    """Directory explanation paired with the real scanned file tree."""

    path: str
    depth: int
    role: str
    importance: Literal["core", "supporting", "skippable"]
    reason: str


class ProjectManual(BaseModel):
    """Stable first-pass project manual used before follow-up questions."""

    title: str = ""
    overview: ProjectSummary | None = None
    technology_stack: list[StackExplanation] = Field(default_factory=list)
    modules: list[ProjectManualModule] = Field(default_factory=list)
    entrypoints: list[ProjectManualEntrypoint] = Field(default_factory=list)
    directory_tree: list[FileTreeEntry] = Field(default_factory=list)
    key_directories: list[ProjectManualDirectory] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    generated_by: str = "ProjectManualBuilder"


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
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    read_files: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentRunRequest(BaseModel):
    """Input for the minimal LLM agent loop."""

    project_path: str
    question: str = "这个项目是干什么的？我应该怎么运行，并从哪些文件开始看？"
    max_steps: int = 6
    project_manual_context: ProjectManual | None = None


class AgentStep(BaseModel):
    """One visible step in the minimal agent loop."""

    index: int
    kind: Literal["llm", "tool", "final", "fallback"]
    title: str
    summary: str
    tool_name: str | None = None
    status: Literal["success", "error"] = "success"


class AnalysisPlanItem(BaseModel):
    """One deterministic planner step for a codebase understanding task."""

    order: int
    actor: str
    title: str
    description: str
    tool: str | None = None
    expected_output: str
    status: Literal["pending", "completed", "skipped"] = "completed"


class ContextSnapshot(BaseModel):
    """A compact view of the context selected for the current analysis task."""

    project_context: list[str] = Field(default_factory=list)
    task_context: list[str] = Field(default_factory=list)
    symbol_context: list[str] = Field(default_factory=list)
    memory_context: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    read_files: list[str] = Field(default_factory=list)


class ProjectReport(BaseModel):
    """Structured project understanding report generated from tools and context."""

    title: str = ""
    project_map: str = ""
    module_summaries: list[str] = Field(default_factory=list)
    key_entrypoints: list[str] = Field(default_factory=list)
    reading_route: list[ReadingPathItem] = Field(default_factory=list)
    call_chain_candidates: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    generated_by: str = "ReportWriter"


AskIntent = Literal[
    "project_overview",
    "module_explanation",
    "file_explanation",
    "call_chain",
    "api_usage",
    "configuration",
    "tech_stack",
]


class ProjectMemoryOverview(BaseModel):
    """Reusable project-level memory generated from the first report."""

    positioning: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class ModuleMemorySummary(BaseModel):
    """Module-level memory used by Ask mode retrieval."""

    name: str
    responsibility: str
    entry_files: list[str] = Field(default_factory=list)
    controller_files: list[str] = Field(default_factory=list)
    service_files: list[str] = Field(default_factory=list)
    view_files: list[str] = Field(default_factory=list)
    api_files: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)


class FileMemorySummary(BaseModel):
    """File-level memory used by Ask mode retrieval."""

    path: str
    responsibility: str
    role: str = ""
    symbols: list[str] = Field(default_factory=list)


class ApiIndexEntry(BaseModel):
    """API endpoint and frontend call index entry."""

    path: str
    method: str | None = None
    backend_method: str | None = None
    backend_file: str | None = None
    frontend_calls: list[str] = Field(default_factory=list)


class FlowIndexEntry(BaseModel):
    """Candidate implementation flow entry."""

    name: str
    kind: str
    steps: list[str] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class ProjectMemory(BaseModel):
    """Structured memory generated from the first project understanding report."""

    project_id: str
    project_name: str
    project_path: str
    project_memory: ProjectMemoryOverview = Field(default_factory=ProjectMemoryOverview)
    module_summaries: list[ModuleMemorySummary] = Field(default_factory=list)
    file_summaries: list[FileMemorySummary] = Field(default_factory=list)
    api_index: list[ApiIndexEntry] = Field(default_factory=list)
    flow_index: list[FlowIndexEntry] = Field(default_factory=list)
    updated_at: str = ""


class SessionMemoryTurn(BaseModel):
    """One Ask mode turn remembered for follow-up questions."""

    question: str
    intent: AskIntent
    referenced_files: list[str] = Field(default_factory=list)
    referenced_apis: list[str] = Field(default_factory=list)
    answer_summary: str = ""


class SessionMemory(BaseModel):
    """Short project session memory used by Ask mode."""

    project_id: str
    turns: list[SessionMemoryTurn] = Field(default_factory=list)
    updated_at: str = ""


class AskModeRequest(BaseModel):
    """Input for the report-side Ask mode."""

    project_path: str
    question: str
    session_memory: SessionMemory | None = None


class AskModeResult(BaseModel):
    """Evidence-grounded answer from Ask mode."""

    project_id: str
    project_name: str
    question: str
    intent: AskIntent
    answer: str
    related_files: list[str] = Field(default_factory=list)
    implementation_path: list[str] = Field(default_factory=list)
    key_code_notes: list[str] = Field(default_factory=list)
    references: list[EvidenceRef] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    trace_events: list[TraceEvent] = Field(default_factory=list)
    session_memory: SessionMemory = Field(default_factory=lambda: SessionMemory(project_id=""))
    warnings: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    """A visible execution trace event for the agent task."""

    index: int
    stage: str
    title: str
    summary: str
    status: Literal["success", "error"] = "success"
    tool_name: str | None = None


class AgentRunResult(BaseModel):
    """Result from the minimal LLM agent loop."""

    task_id: str = ""
    project_name: str
    question: str
    skill: str
    analysis_goal: str = ""
    analysis_plan: list[AnalysisPlanItem] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    context_snapshot: ContextSnapshot = Field(default_factory=ContextSnapshot)
    project_manual: ProjectManual = Field(default_factory=ProjectManual)
    project_memory: ProjectMemory | None = None
    report: ProjectReport = Field(default_factory=ProjectReport)
    trace_events: list[TraceEvent] = Field(default_factory=list)
    final_answer: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    read_files: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    agent_steps: list[AgentStep] = Field(default_factory=list)
    used_llm: bool = False
    fallback_used: bool = False
    fallback_result: ProjectInterpretationResult | None = None
