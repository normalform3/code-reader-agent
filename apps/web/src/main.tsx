import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type StackTag = {
  name: string;
  source: string;
  confidence: number;
};

type Entrypoint = {
  path: string;
  kind: string;
  exists: boolean;
};

type ProjectSummary = {
  one_liner: string;
  audience: string;
  problem: string;
  confidence: number;
  evidence: string[];
};

type StackExplanation = {
  name: string;
  category: string;
  purpose: string;
  evidence_source: string;
  confidence: number;
};

type DirectoryInsight = {
  path: string;
  role: string;
  importance: "core" | "supporting" | "skippable";
  reason: string;
};

type ReadingRecommendation = {
  path: string;
  action: "read_first" | "skip_for_now";
  reason: string;
  priority: number;
};

type FileTreeEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  depth: number;
};

type RepoMapModule = {
  id: string;
  name: string;
  type: string;
  description: string;
  responsibility: string;
  key_files: string[];
  entry_files: string[];
  reading_priority: number;
  confidence: number;
  evidence: string[];
};

type RepoMapFile = {
  path: string;
  role: string;
  language: string | null;
  framework: string | null;
  importance_score: number;
  summary: string;
  related_modules: string[];
  evidence: string[];
};

type RepoMapEvidence = {
  id: string;
  source: string;
  path: string;
  reason: string;
  collected_by_tool: string;
  start_line: number | null;
  end_line: number | null;
  excerpt: string | null;
  collected_at: string | null;
};

type RepoMap = {
  project_name: string;
  project_path: string;
  project_summary: ProjectSummary | null;
  detected_stack: StackTag[];
  stack_explanations: StackExplanation[];
  directory_insights: DirectoryInsight[];
  reading_recommendations: ReadingRecommendation[];
  package_manager: string | null;
  java_build_tool: string | null;
  run_scripts: Record<string, string>;
  entrypoints: Entrypoint[];
  modules: RepoMapModule[];
  files: RepoMapFile[];
  file_tree: FileTreeEntry[];
  api_endpoints: string[];
  api_flows: string[];
  auth_flows: string[];
  stores: string[];
  controllers: string[];
  services: string[];
  repositories: string[];
  components: string[];
  evidence: RepoMapEvidence[];
  warnings: string[];
  generated_at: string;
};

type ReadingPathItem = {
  order: number;
  path: string;
  reason: string;
};

type AnalysisPlanItem = {
  order: number;
  actor: string;
  title: string;
  description: string;
  tool: string | null;
  expected_output: string;
  status: "pending" | "completed" | "skipped";
};

type ContextSnapshot = {
  project_context: string[];
  task_context: string[];
  symbol_context: string[];
  memory_context: string[];
  evidence_count: number;
  read_files: string[];
};

type ProjectReport = {
  title: string;
  project_map: string;
  module_summaries: string[];
  key_entrypoints: string[];
  reading_route: ReadingPathItem[];
  call_chain_candidates: string[];
  evidence: Array<{
    path: string;
    reason: string;
    source: string;
    start_line: number | null;
    end_line: number | null;
    excerpt: string | null;
  }>;
  uncertainties: string[];
  generated_by: string;
};

type EvidenceRef = {
  path: string;
  reason: string;
  source: string;
  start_line: number | null;
  end_line: number | null;
  excerpt: string | null;
};

type ProjectManualModule = {
  id: string;
  name: string;
  type: string;
  responsibility: string;
  key_files: string[];
  entry_files: string[];
  confidence: number;
};

type ProjectManualEntrypoint = {
  path: string;
  kind: string;
  reason: string;
};

type ProjectManualDirectory = {
  path: string;
  depth: number;
  role: string;
  importance: "core" | "supporting" | "skippable";
  reason: string;
};

type ProjectManual = {
  title: string;
  overview: ProjectSummary | null;
  technology_stack: StackExplanation[];
  modules: ProjectManualModule[];
  entrypoints: ProjectManualEntrypoint[];
  directory_tree: FileTreeEntry[];
  key_directories: ProjectManualDirectory[];
  evidence: EvidenceRef[];
  uncertainties: string[];
  generated_by: string;
};

type TraceEvent = {
  index: number;
  stage: string;
  title: string;
  summary: string;
  status: "success" | "error";
  tool_name: string | null;
};

type Interpretation = {
  task_id?: string;
  project_name: string;
  question: string;
  skill: string;
  analysis_goal?: string;
  analysis_plan?: AnalysisPlanItem[];
  selected_skills?: string[];
  context_snapshot?: ContextSnapshot;
  project_manual?: ProjectManual;
  project_memory?: ProjectMemory | null;
  report?: ProjectReport;
  trace_events?: TraceEvent[];
  prompt_version?: string;
  overview?: string;
  setup_summary?: string;
  final_answer?: string;
  used_llm?: boolean;
  fallback_used?: boolean;
  reading_path?: ReadingPathItem[];
  evidence: EvidenceRef[];
  tool_calls: Array<{
    tool_name: string;
    input_summary: string;
    output_summary: string;
    status: "success" | "error";
    error: string | null;
  }>;
  read_files: string[];
  suggested_questions: string[];
  warnings: string[];
  agent_steps?: Array<{
    index: number;
    kind: "llm" | "tool" | "final" | "fallback";
    title: string;
    summary: string;
    tool_name: string | null;
    status: "success" | "error";
  }>;
};

type ProjectMemoryOverview = {
  positioning: string;
  tech_stack: string[];
  startup_commands: string[];
  modules: string[];
};

type ProjectMemory = {
  project_id: string;
  project_name: string;
  project_path: string;
  project_memory: ProjectMemoryOverview;
  updated_at: string;
};

type AskIntent =
  | "project_overview"
  | "module_explanation"
  | "file_explanation"
  | "call_chain"
  | "api_usage"
  | "configuration"
  | "tech_stack";

type SessionMemoryTurn = {
  question: string;
  intent: AskIntent;
  referenced_files: string[];
  referenced_apis: string[];
  answer_summary: string;
};

type SessionMemory = {
  project_id: string;
  turns: SessionMemoryTurn[];
  updated_at: string;
};

type AskModeResult = {
  project_id: string;
  project_name: string;
  question: string;
  intent: AskIntent;
  answer: string;
  related_files: string[];
  implementation_path: string[];
  key_code_notes: string[];
  references: EvidenceRef[];
  tool_calls: Array<{
    tool_name: string;
    input_summary: string;
    output_summary: string;
    status: "success" | "error";
    error: string | null;
    reason: string | null;
  }>;
  trace_events: TraceEvent[];
  session_memory: SessionMemory;
  warnings: string[];
};

type GitHubImportResult = {
  project_name: string;
  project_path: string;
  github_url: string;
  repository: string;
  reused_cache: boolean;
  warnings: string[];
};

type ProjectSession = {
  id: string;
  title: string;
  project_name: string;
  project_path: string;
  github_url: string | null;
  repository: string | null;
  status: string;
  last_question: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

type RegistryDetailSection = {
  title: string;
  items: string[];
};

type RegistryItem = {
  id: string;
  name: string;
  description: string;
  notes: string;
  details: RegistryDetailSection[];
  enabled: boolean;
  builtin: boolean;
  created_at: string;
  updated_at: string;
};

type Status = "empty" | "importing" | "loading" | "ready" | "error";
type RegistryKind = "tools" | "skills";
type SidebarView = "history" | "files";
type AskMessage = {
  id: string;
  role: "user" | "assistant";
  body: string;
  meta?: string;
};
type FileTreeNode = FileTreeEntry & {
  children: FileTreeNode[];
};

const DEFAULT_QUESTION = "请先为这个仓库生成项目说明书：这是一个什么项目（总览）？用了什么技术栈？每个模块的作用是什么？项目入口在哪里？请给出真实目录树，并解释每个关键目录的作用。";

function App() {
  const [registryModal, setRegistryModal] = useState<RegistryKind | null>(null);
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarView, setSidebarView] = useState<SidebarView>("history");
  const [projectPath, setProjectPath] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [githubImport, setGithubImport] = useState<GitHubImportResult | null>(null);
  const [question, setQuestion] = useState("");
  const [askMessages, setAskMessages] = useState<AskMessage[]>([]);
  const [repoMap, setRepoMap] = useState<RepoMap | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [askResult, setAskResult] = useState<AskModeResult | null>(null);
  const [askSessionMemory, setAskSessionMemory] = useState<SessionMemory | null>(null);
  const [projectManual, setProjectManual] = useState<ProjectManual | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("empty");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshSessions();
  }, []);

  const activeSession = sessions.find((item) => item.id === activeSessionId) ?? null;

  async function refreshSessions() {
    try {
      const result = await getJson<ProjectSession[]>("/api/projects/history");
      setSessions(result);
      if (!activeSessionId && result.length > 0) {
        setActiveSessionId(result[0].id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取历史项目失败。");
    }
  }

  async function analyzeProject(nextProjectPath: string, nextQuestion = DEFAULT_QUESTION) {
    setStatus("loading");
    setError(null);
    setInterpretation(null);
    setAskResult(null);
    setProjectPath(nextProjectPath);

    const [repoMapResult, interpretationResult] = await Promise.all([
      postJson<RepoMap>("/api/projects/repo-map", { project_path: nextProjectPath }),
      postJson<Interpretation>("/api/agent/run", {
        project_path: nextProjectPath,
        question: nextQuestion,
      }),
    ]);
    setRepoMap(repoMapResult);
    setInterpretation(interpretationResult);
    setProjectManual(interpretationResult.project_manual ?? null);
    setSelectedModuleId(repoMapResult.modules[0]?.id ?? null);
    setSidebarView("files");
    setStatus("ready");
    return { repoMapResult, interpretationResult };
  }

  async function handleGithubImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!githubUrl.trim()) {
      setError("请先输入公开 GitHub 仓库链接。");
      setStatus("error");
      return;
    }

    setStatus("importing");
    setError(null);
    setRepoMap(null);
    setInterpretation(null);
    setAskResult(null);
    setAskSessionMemory(null);
    setProjectManual(null);
    setAskMessages([]);
    setSelectedModuleId(null);
    setGithubImport(null);

    try {
      const importedProject = await postJson<GitHubImportResult>("/api/projects/import-github", {
        github_url: githubUrl.trim(),
      });
      setGithubImport(importedProject);
      const analysisQuestion = question.trim() || DEFAULT_QUESTION;
      const { repoMapResult } = await analyzeProject(importedProject.project_path, analysisQuestion);
      setAskMessages([
        {
          id: `${Date.now()}-manual`,
          role: "assistant",
          body:
            interpretationText(repoMapResult.project_summary?.one_liner) ||
            `${repoMapResult.project_name} 的项目说明书已生成，可以继续在右侧追问。`,
          meta: "项目说明书",
        },
      ]);
      const session = await postJson<ProjectSession>("/api/projects/history", {
        project_name: repoMapResult.project_name,
        project_path: importedProject.project_path,
        title: importedProject.repository,
        github_url: importedProject.github_url,
        repository: importedProject.repository,
        status: "ready",
        last_question: question.trim() || null,
      });
      setActiveSessionId(session.id);
      await refreshSessions();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "导入或分析失败，请检查 GitHub 链接和本地 API。";
      setError(message);
      setStatus("error");
    }
  }

  async function handleSelectSession(session: ProjectSession) {
    setActiveSessionId(session.id);
    setGithubImport(null);
    setGithubUrl(session.github_url ?? "");
    setQuestion("");
    setSidebarView("files");
    try {
      const { repoMapResult, interpretationResult } = await analyzeProject(session.project_path, DEFAULT_QUESTION);
      setAskMessages([
        {
          id: `${Date.now()}-restore`,
          role: "assistant",
          body:
            interpretationText(interpretationResult.report?.project_map) ||
            interpretationText(interpretationResult.final_answer) ||
            `${repoMapResult.project_name} 已恢复，项目文件树和说明书已刷新。`,
          meta: "历史项目",
        },
      ]);
      await patchJson<ProjectSession>(`/api/projects/history/${session.id}`, {
          status: "ready",
          last_question: session.last_question,
          last_error: null,
      });
      await refreshSessions();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "恢复历史项目失败。";
      setError(message);
      setStatus("error");
      await patchJson<ProjectSession>(`/api/projects/history/${session.id}`, {
        status: "error",
        last_error: message,
      }).catch(() => null);
      await refreshSessions();
    }
  }

  async function handleDeleteSession(session: ProjectSession) {
    await deleteJson(`/api/projects/history/${session.id}`);
    if (session.id === activeSessionId) {
      setActiveSessionId(null);
      setRepoMap(null);
      setInterpretation(null);
      setAskResult(null);
      setAskSessionMemory(null);
      setProjectManual(null);
      setAskMessages([]);
      setProjectPath("");
      setStatus("empty");
    }
    await refreshSessions();
  }

  async function handleAsk() {
    if (!projectPath.trim()) {
      return;
    }
    setStatus("loading");
    setError(null);
    const askedQuestion = question.trim();
    setAskMessages((current) => [
      ...current,
      {
        id: `${Date.now()}-user`,
        role: "user",
        body: askedQuestion,
      },
    ]);
    try {
      const result = await postJson<AskModeResult>("/api/agent/ask", {
        project_path: projectPath.trim(),
        question: askedQuestion,
        session_memory: askSessionMemory,
      });
      setAskResult(result);
      setAskSessionMemory(result.session_memory);
      setAskMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          body: askResultText(result),
          meta: `Ask · ${intentLabel(result.intent)}`,
        },
      ]);
      setStatus("ready");
      if (activeSessionId) {
        await patchJson<ProjectSession>(`/api/projects/history/${activeSessionId}`, {
          status: "ready",
          last_question: question,
          last_error: null,
        });
        await refreshSessions();
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "提问失败，请检查本地 API 是否已启动。";
      setError(message);
      setStatus("error");
      if (activeSessionId) {
        await patchJson<ProjectSession>(`/api/projects/history/${activeSessionId}`, {
          status: "error",
          last_error: message,
        }).catch(() => null);
        await refreshSessions();
      }
    }
  }

  return (
    <main className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <Sidebar
        activeSessionId={activeSessionId}
        collapsed={sidebarCollapsed}
        fileTree={repoMap?.file_tree ?? projectManual?.directory_tree ?? []}
        githubUrl={githubUrl}
        onDeleteSession={handleDeleteSession}
        onGithubImport={handleGithubImport}
        onOpenRegistry={setRegistryModal}
        onSelectSession={handleSelectSession}
        onSetGithubUrl={setGithubUrl}
        onSetView={setSidebarView}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        sessions={sessions}
        status={status}
        view={sidebarView}
      />

      <ProjectWorkspace
        activeSession={activeSession}
        askMessages={askMessages}
        askResult={askResult}
        error={error}
        githubImport={githubImport}
        interpretation={interpretation}
        onAsk={handleAsk}
        onSelectModule={setSelectedModuleId}
        onSetQuestion={setQuestion}
        projectManual={projectManual}
        question={question}
        repoMap={repoMap}
        selectedModuleId={selectedModuleId}
        status={status}
      />

      {registryModal ? <RegistryModal kind={registryModal} onClose={() => setRegistryModal(null)} /> : null}
    </main>
  );
}

function Sidebar({
  activeSessionId,
  collapsed,
  fileTree,
  githubUrl,
  onDeleteSession,
  onGithubImport,
  onOpenRegistry,
  onSelectSession,
  onSetGithubUrl,
  onSetView,
  onToggleCollapsed,
  sessions,
  status,
  view,
}: {
  activeSessionId: string | null;
  collapsed: boolean;
  fileTree: FileTreeEntry[];
  githubUrl: string;
  onDeleteSession: (session: ProjectSession) => void;
  onGithubImport: (event: FormEvent<HTMLFormElement>) => void;
  onOpenRegistry: (kind: RegistryKind) => void;
  onSelectSession: (session: ProjectSession) => void;
  onSetGithubUrl: (url: string) => void;
  onSetView: (view: SidebarView) => void;
  onToggleCollapsed: () => void;
  sessions: ProjectSession[];
  status: Status;
  view: SidebarView;
}) {
  return (
    <aside className={collapsed ? "sidebar collapsed" : "sidebar"}>
      <div className="sidebar-top">
        <div className="brand-row">
          <div className="brand-mark">CR</div>
          <div>
            <h1>CodeReader</h1>
            <p>会话式代码库理解 Agent</p>
          </div>
          <button className="icon-button sidebar-toggle" onClick={onToggleCollapsed} title={collapsed ? "展开侧边栏" : "收起侧边栏"} type="button">
            {collapsed ? ">" : "<"}
          </button>
        </div>

        <form className="scan-form" onSubmit={onGithubImport}>
          <label htmlFor="github-url">新建分析</label>
          <input
            id="github-url"
            value={githubUrl}
            onChange={(event) => onSetGithubUrl(event.target.value)}
            placeholder="https://github.com/owner/repo"
          />
          <button type="submit" disabled={status === "importing" || status === "loading"}>
            {status === "importing" ? "正在下载..." : status === "loading" ? "正在分析..." : "导入并分析"}
          </button>
          <p className="muted">公开 GitHub 仓库会保存为左侧项目会话。</p>
        </form>
      </div>

      <div className="sidebar-tabs" role="tablist" aria-label="左侧视图">
        <button className={view === "history" ? "sidebar-tab active" : "sidebar-tab"} onClick={() => onSetView("history")} type="button">
          历史项目
        </button>
        <button className={view === "files" ? "sidebar-tab active" : "sidebar-tab"} onClick={() => onSetView("files")} type="button">
          当前文件
        </button>
      </div>

      <div className="session-section">
        {view === "history" ? (
          <>
            <SectionTitle title="历史项目" />
            <div className="session-list">
              {sessions.length > 0 ? (
                sessions.map((session) => (
                  <div className={session.id === activeSessionId ? "session-item active" : "session-item"} key={session.id}>
                    <button type="button" onClick={() => onSelectSession(session)}>
                      <strong>{session.title}</strong>
                      <span>{session.repository ?? session.project_name}</span>
                      <small>
                        {session.status} · {formatDate(session.updated_at)}
                      </small>
                    </button>
                    <button className="ghost-danger" type="button" onClick={() => onDeleteSession(session)}>
                      移除
                    </button>
                  </div>
                ))
              ) : (
                <div className="quiet-empty">还没有历史项目。导入一个公开仓库后会出现在这里。</div>
              )}
            </div>
          </>
        ) : (
          <>
            <SectionTitle title="当前项目文件" />
            <SidebarFileTree entries={fileTree} />
          </>
        )}
      </div>

      <nav className="sidebar-nav">
        <button className="nav-button active" type="button">
          项目工作台
        </button>
        <button className="nav-button" type="button" onClick={() => onOpenRegistry("tools")}>
          工具管理
        </button>
        <button className="nav-button" type="button" onClick={() => onOpenRegistry("skills")}>
          Skill 管理
        </button>
      </nav>
    </aside>
  );
}

function SidebarFileTree({ entries }: { entries: FileTreeEntry[] }) {
  const tree = useMemo(() => buildFileTree(entries), [entries]);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpandedPaths(new Set(entries.filter((entry) => entry.kind === "directory" && entry.depth === 0).map((entry) => entry.path)));
  }, [entries]);

  if (!entries.length) {
    return <div className="quiet-empty">选择或导入项目后，这里会显示当前项目文件树。</div>;
  }

  function toggleDirectory(path: string) {
    setExpandedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  return (
    <div className="sidebar-file-tree">
      {tree.map((node) => (
        <SidebarFileNode expandedPaths={expandedPaths} key={node.path} node={node} onToggle={toggleDirectory} />
      ))}
      {entries.length > 220 ? <p className="muted">仅展示前 220 项，完整目录树见中间项目说明书。</p> : null}
    </div>
  );
}

function SidebarFileNode({
  expandedPaths,
  node,
  onToggle,
}: {
  expandedPaths: Set<string>;
  node: FileTreeNode;
  onToggle: (path: string) => void;
}) {
  const expanded = expandedPaths.has(node.path);
  const hasChildren = node.children.length > 0;
  const label = node.name || node.path.split("/").pop() || node.path;

  return (
    <div>
      {node.kind === "directory" ? (
        <button className="sidebar-file-row directory" onClick={() => onToggle(node.path)} style={{ paddingLeft: `${node.depth * 10 + 8}px` }} type="button">
          <span className={expanded ? "tree-chevron expanded" : "tree-chevron"}>{hasChildren ? ">" : ""}</span>
          <code title={node.path}>{label}</code>
        </button>
      ) : (
        <div className="sidebar-file-row file" style={{ paddingLeft: `${node.depth * 10 + 8}px` }}>
          <span className="tree-file-dot" />
          <code title={node.path}>{label}</code>
        </div>
      )}
      {node.kind === "directory" && expanded
        ? node.children.map((child) => (
            <SidebarFileNode expandedPaths={expandedPaths} key={child.path} node={child} onToggle={onToggle} />
          ))
        : null}
    </div>
  );
}

function ProjectWorkspace({
  activeSession,
  askMessages,
  askResult,
  error,
  githubImport,
  interpretation,
  onAsk,
  onSelectModule,
  onSetQuestion,
  projectManual,
  question,
  repoMap,
  selectedModuleId,
  status,
}: {
  activeSession: ProjectSession | null;
  askMessages: AskMessage[];
  askResult: AskModeResult | null;
  error: string | null;
  githubImport: GitHubImportResult | null;
  interpretation: Interpretation | null;
  onAsk: () => void;
  onSelectModule: (moduleId: string) => void;
  onSetQuestion: (question: string) => void;
  projectManual: ProjectManual | null;
  question: string;
  repoMap: RepoMap | null;
  selectedModuleId: string | null;
  status: Status;
}) {
  const selectedModule = useMemo(() => {
    if (!repoMap) {
      return null;
    }
    return repoMap.modules.find((module) => module.id === selectedModuleId) ?? repoMap.modules[0] ?? null;
  }, [repoMap, selectedModuleId]);

  const evidenceById = useMemo(() => {
    return new Map(repoMap?.evidence.map((item) => [item.id, item]) ?? []);
  }, [repoMap]);

  const selectedModuleFiles = useMemo(() => {
    if (!repoMap || !selectedModule) {
      return [];
    }
    const fileSet = new Set(selectedModule.key_files);
    return repoMap.files.filter((file) => fileSet.has(file.path));
  }, [repoMap, selectedModule]);

  const statusLabel: Record<Status, string> = {
    empty: "未扫描",
    importing: "下载中",
    loading: "分析中",
    ready: "已完成",
    error: "出错",
  };
  const manualOverview = projectManual?.overview ?? repoMap?.project_summary ?? null;

  return (
    <section className="workspace-shell">
      <section className="map-panel">
        <header className="workspace-header">
          <div>
            <p className="kicker">Project Session</p>
            <h2>{repoMap?.project_name ?? activeSession?.title ?? "输入公开 GitHub 仓库链接"}</h2>
            <span>{githubImport?.github_url ?? activeSession?.github_url ?? "像会话一样保存每个项目的分析历史。"}</span>
          </div>
          <div className="status-pill" data-status={status}>
            {statusLabel[status]}
          </div>
        </header>

        {error ? <div className="error-box">{error}</div> : null}

        <section className="overview-panel">
          <div className="summary-card">
            <div className="detail-heading">
              <div>
                <p className="kicker">代码库总览</p>
                <h3>{manualOverview?.one_liner ?? "扫描完成后生成项目一句话解释"}</h3>
              </div>
              {manualOverview ? <span>{Math.round(manualOverview.confidence * 100)}% 置信度</span> : null}
            </div>
            <div className="summary-grid">
              <div>
                <strong>面向谁</strong>
                <p>{manualOverview?.audience ?? "等待 README、配置和入口文件证据。"}</p>
              </div>
              <div>
                <strong>解决什么问题</strong>
                <p>{manualOverview?.problem ?? "证据不足时会明确提示低置信度。"}</p>
              </div>
            </div>
          </div>

          <ProjectManualCard manual={projectManual} />
        </section>

        <div className="module-grid">
          {repoMap?.modules
            .slice()
            .sort((left, right) => left.reading_priority - right.reading_priority || left.name.localeCompare(right.name))
            .map((module) => (
              <button
                className={module.id === selectedModule?.id ? "module-card active" : "module-card"}
                key={module.id}
                onClick={() => onSelectModule(module.id)}
                type="button"
              >
                <span>{module.type}</span>
                <strong>{module.name}</strong>
                <small>
                  优先级 {module.reading_priority} · {module.key_files.length} 个核心文件
                </small>
                <p>{module.responsibility}</p>
              </button>
            )) ?? <EmptyState title="暂无模块" body="扫描项目后，将生成确定性的模块地图。" />}
        </div>

        <div className="detail-panel">
          {selectedModule ? (
            <>
              <div className="detail-heading">
                <div>
                  <p className="kicker">当前模块</p>
                  <h3>{selectedModule.name}</h3>
                </div>
                <span>{Math.round(selectedModule.confidence * 100)}% 置信度</span>
              </div>
              <p>{selectedModule.responsibility}</p>
              <div className="file-table">
                {selectedModuleFiles.map((file) => (
                  <div className="file-row with-meta" key={file.path}>
                    <code>{file.path}</code>
                    <span>
                      {file.role}
                      {file.language ? ` · ${file.language}` : ""}
                      {file.framework ? ` · ${file.framework}` : ""}
                    </span>
                  </div>
                ))}
              </div>
              <div className="evidence-snippets">
                <h4>模块证据</h4>
                {selectedModule.evidence.length > 0 ? (
                  selectedModule.evidence.map((evidenceId) => {
                    const evidence = evidenceById.get(evidenceId);
                    return evidence ? <EvidenceSnippet evidence={evidence} key={evidence.id} /> : null;
                  })
                ) : (
                  <p className="muted">该模块目前只有路径规则推断，暂无片段证据。</p>
                )}
              </div>
            </>
          ) : (
            <EmptyState title="模块详情" body="模块证据和关键文件会显示在这里。" />
          )}
        </div>
      </section>

      <AgentPanel
        askMessages={askMessages}
        askResult={askResult}
        interpretation={interpretation}
        onAsk={onAsk}
        onSetQuestion={onSetQuestion}
        question={question}
        repoMap={repoMap}
        status={status}
      />
    </section>
  );
}

function AgentPanel({
  askMessages,
  askResult,
  interpretation,
  onAsk,
  onSetQuestion,
  question,
  repoMap,
  status,
}: {
  askMessages: AskMessage[];
  askResult: AskModeResult | null;
  interpretation: Interpretation | null;
  onAsk: () => void;
  onSetQuestion: (question: string) => void;
  question: string;
  repoMap: RepoMap | null;
  status: Status;
}) {
  const latestAnswer =
    interpretation?.report?.project_map ??
    interpretation?.final_answer ??
    interpretation?.overview ??
    "导入项目后，右侧会保留 Ask 对话；项目说明书固定展示在中间主区。";
  return (
    <aside className="agent-panel">
      <header className="ask-header">
        <div>
          <p className="kicker">Ask</p>
          <h3>CodeReader Copilot</h3>
        </div>
        <span className="ask-status">
          {askResult ? `Ask · ${intentLabel(askResult.intent)}` : `${interpretation?.used_llm ? "LLM" : "规则"} · ${interpretation?.task_id ?? "待命"}`}
        </span>
      </header>

      <div className="ask-scroll-area">
        <div className="ask-thread">
          {askMessages.length > 0 ? (
            askMessages.map((message) => (
              <article className={`ask-message ${message.role}`} key={message.id}>
                <span>{message.role === "user" ? "你" : message.meta ?? "Agent"}</span>
                <p>{message.body}</p>
              </article>
            ))
          ) : (
            <article className="ask-message assistant">
              <span>Agent</span>
              <p>{latestAnswer}</p>
            </article>
          )}
          {interpretation?.fallback_used ? <span className="warning-note">LLM Agent 已降级为确定性解释。</span> : null}
        </div>

        <div className="ask-context">
        <details>
          <summary>{askResult ? "Ask Trace" : "Planner / Context"}</summary>
          <div className="step-list">
            {askResult?.trace_events.slice(0, 6).map((item) => (
              <div className="step-row" data-status={item.status} key={`${item.index}-${item.title}`}>
                <span>{item.stage}</span>
                <strong>{item.title}</strong>
                <small>{item.summary}</small>
              </div>
            )) ??
              interpretation?.analysis_plan?.slice(0, 4).map((item) => (
              <div className="step-row" data-status="success" key={`${item.order}-${item.title}`}>
                <span>{item.actor}</span>
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </div>
            )) ?? <span className="muted">创建分析任务后会显示 Planner 输出</span>}
          </div>
          <div className="mini-list">
            {askResult ? <code>{intentLabel(askResult.intent)}</code> : null}
            {askResult?.tool_calls.slice(0, 4).map((call, index) => (
              <code key={`${call.tool_name}-${index}`}>{call.tool_name}</code>
            ))}
            {interpretation?.selected_skills?.map((skill) => <code key={skill}>{skill}</code>) ?? null}
            {askResult ? <span className="muted">{askResult.references.length} 条 Ask evidence · {askResult.session_memory.turns.length} 轮记忆</span> : null}
            {interpretation?.context_snapshot ? (
              <span className="muted">
                  {interpretation.context_snapshot.evidence_count} 条 evidence · {interpretation.context_snapshot.read_files.length} 个已读取文件
                </span>
              ) : null}
            </div>
          </details>

        <details>
          <summary>{askResult ? "相关文件 / 实现路径" : "阅读路径"}</summary>
          <ol>
            {askResult?.implementation_path.slice(0, 8).map((path, index) => (
              <li key={`${index}-${path}`}>
                <code>{path}</code>
                <span>{askResult.related_files.includes(path) ? "相关文件" : "候选链路"}</span>
              </li>
            )) ??
              (interpretation?.report?.reading_route ?? interpretation?.reading_path)?.slice(0, 6).map((item) => (
              <li key={`${item.order}-${item.path}`}>
                <code>{item.path}</code>
                <span>{item.reason}</span>
              </li>
            ))}
          </ol>
        </details>
        </div>
      </div>

      <div className="ask-composer">
        <textarea placeholder="向当前项目提问..." value={question} onChange={(event) => onSetQuestion(event.target.value)} />
        <button onClick={onAsk} disabled={!repoMap || status === "importing" || status === "loading" || !question.trim()} type="button">
          {status === "loading" ? "分析中..." : "发送"}
        </button>
      </div>
    </aside>
  );
}

function ProjectManualCard({ manual }: { manual: ProjectManual | null }) {
  const keyDirectories = useMemo(() => {
    return manual?.key_directories.filter(isHighLevelDirectoryInsight).slice(0, 8) ?? [];
  }, [manual]);

  if (!manual) {
    return (
      <div className="manual-card">
        <div className="detail-heading">
          <div>
            <p className="kicker">项目说明书</p>
            <h3>等待首次扫描生成说明书</h3>
          </div>
        </div>
        <p className="muted">导入项目后，Agent 会先生成总览、技术栈、模块、入口和真实目录树解释。</p>
      </div>
    );
  }

  return (
    <div className="manual-card">
      <div className="detail-heading">
        <div>
          <p className="kicker">项目说明书</p>
          <h3>{manual.title}</h3>
        </div>
        <span>{manual.generated_by}</span>
      </div>

      <div className="manual-grid">
        <ManualColumn title="技术栈" empty="未识别明确技术栈">
          {manual.technology_stack.slice(0, 6).map((item) => (
            <div className="manual-row" key={`${item.name}-${item.evidence_source}`}>
              <strong>{item.name}</strong>
              <span>{item.category}</span>
              <p>{item.purpose}</p>
            </div>
          ))}
        </ManualColumn>

        <ManualColumn title="模块作用" empty="暂无模块说明">
          {manual.modules.slice(0, 6).map((module) => (
            <div className="manual-row" key={module.id}>
              <strong>{module.name}</strong>
              <span>{module.type}</span>
              <p>{module.responsibility}</p>
            </div>
          ))}
        </ManualColumn>

        <ManualColumn title="项目入口" empty="暂无入口候选">
          {manual.entrypoints.slice(0, 6).map((entrypoint) => (
            <div className="manual-row" key={`${entrypoint.kind}-${entrypoint.path}`}>
              <code>{entrypoint.path}</code>
              <span>{entrypoint.kind}</span>
              <p>{entrypoint.reason}</p>
            </div>
          ))}
        </ManualColumn>
      </div>

      <div className="manual-tree">
        <div>
          <h4>真实目录树</h4>
          <div className="tree-list compact">
            {manual.directory_tree.slice(0, 42).map((entry) => (
              <div className="tree-row" key={entry.path} style={{ paddingLeft: `${entry.depth * 12 + 8}px` }}>
                <span>{entry.kind === "directory" ? "dir" : "file"}</span>
                <code>{entry.path}</code>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h4>关键目录解释</h4>
          <div className="manual-directory-list">
            {keyDirectories.length > 0 ? (
              keyDirectories.map((directory) => (
                <div className="manual-row" key={directory.path}>
                  <code>{directory.path}</code>
                  <span>
                    {directory.role} · {directory.importance}
                  </span>
                  <p>{directory.reason}</p>
                </div>
              ))
            ) : (
              <span className="muted">暂无顶层或典型分层目录解释。</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ManualColumn({ children, empty, title }: { children: React.ReactNode; empty: string; title: string }) {
  return (
    <div className="manual-column">
      <h4>{title}</h4>
      <div className="manual-list">{children || <span className="muted">{empty}</span>}</div>
    </div>
  );
}

function RegistryModal({ kind, onClose }: { kind: RegistryKind; onClose: () => void }) {
  const [items, setItems] = useState<RegistryItem[]>([]);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", description: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const endpoint = kind === "tools" ? "/api/registry/tools" : "/api/registry/skills";
  const title = kind === "tools" ? "工具管理" : "Skill 管理";

  useEffect(() => {
    void refresh();
  }, [kind]);

  async function refresh() {
    try {
      const result = await getJson<RegistryItem[]>(endpoint);
      setItems(result);
      setSelectedId((current) => current ?? result[0]?.id ?? null);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取 registry 失败。");
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.name.trim()) {
      setError("名称不能为空。");
      return;
    }
    await postJson<RegistryItem>(endpoint, draft);
    setDraft({ name: "", description: "", notes: "" });
    await refresh();
  }

  async function handlePatch(item: RegistryItem, patch: Partial<Pick<RegistryItem, "name" | "description" | "notes" | "details" | "enabled">>) {
    const updated = await patchJson<RegistryItem>(`${endpoint}/${item.id}`, patch);
    setItems((current) => current.map((candidate) => (candidate.id === item.id ? updated : candidate)));
    setSelectedId(updated.id);
  }

  async function handleDelete(item: RegistryItem) {
    const result = await deleteJson<RegistryItem | null>(`${endpoint}/${item.id}`);
    if (result) {
      setItems((current) => current.map((candidate) => (candidate.id === item.id ? result : candidate)));
      setSelectedId(result.id);
    } else {
      setItems((current) => {
        const next = current.filter((candidate) => candidate.id !== item.id);
        setSelectedId(next[0]?.id ?? null);
        return next;
      });
    }
  }

  const filteredItems = items.filter((item) => {
    const haystack = `${item.name} ${item.description} ${item.notes}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="registry-modal" role="dialog">
        <header className="registry-modal-header">
          <div>
            <p className="kicker">Local Registry</p>
            <h2>{title}</h2>
            <span>列表只显示名称和描述，点击后查看完整定义。</span>
          </div>
          <div className="registry-header-actions">
            <div className="status-pill" data-status="ready">
              {items.filter((item) => item.enabled).length}/{items.length} 启用
            </div>
            <button className="secondary-button" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </header>

        {error ? <div className="error-box">{error}</div> : null}

        <div className="registry-modal-body">
          <aside className="registry-list-pane">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`搜索${kind === "tools" ? "工具" : "Skill"}`} />
            <form className="registry-create" onSubmit={handleCreate}>
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="自定义名称" />
              <input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="一句话描述" />
              <textarea value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} placeholder="补充说明" />
              <button type="submit">新增自定义项</button>
            </form>

            <div className="registry-list">
              {filteredItems.map((item) => (
                <RegistryListItem
                  active={item.id === selectedItem?.id}
                  item={item}
                  key={item.id}
                  onSelect={() => setSelectedId(item.id)}
                />
              ))}
            </div>
          </aside>

          <RegistryDetailPanel item={selectedItem} onDelete={handleDelete} onPatch={handlePatch} />
        </div>
      </section>
    </div>
  );
}

function RegistryListItem({ active, item, onSelect }: { active: boolean; item: RegistryItem; onSelect: () => void }) {
  return (
    <button className={active ? "registry-list-item active" : "registry-list-item"} onClick={onSelect} type="button">
      <div>
        <strong>{item.name}</strong>
        <span>{item.description || "暂无描述"}</span>
      </div>
      <div className="registry-list-meta">
        <span className={item.builtin ? "registry-badge builtin" : "registry-badge"}>{item.builtin ? "内置" : "自定义"}</span>
        <span className={item.enabled ? "registry-state enabled" : "registry-state"}>{item.enabled ? "启用" : "禁用"}</span>
      </div>
    </button>
  );
}

function RegistryDetailPanel({
  item,
  onDelete,
  onPatch,
}: {
  item: RegistryItem | null;
  onDelete: (item: RegistryItem) => void;
  onPatch: (item: RegistryItem, patch: Partial<Pick<RegistryItem, "name" | "description" | "notes" | "details" | "enabled">>) => void;
}) {
  const [draft, setDraft] = useState<RegistryItem | null>(item);

  useEffect(() => {
    setDraft(item);
  }, [item]);

  if (!item || !draft) {
    return (
      <section className="registry-detail-pane">
        <EmptyState title="暂无条目" body="没有匹配的工具或 skill。" />
      </section>
    );
  }

  function updateDetailSection(index: number, patch: Partial<RegistryDetailSection>) {
    if (!draft) {
      return;
    }
    const details = draft.details.map((section, sectionIndex) =>
      sectionIndex === index ? { ...section, ...patch } : section,
    );
    setDraft({ ...draft, details });
  }

  function addDetailSection() {
    if (!draft) {
      return;
    }
    setDraft({ ...draft, details: [...draft.details, { title: "新增详情", items: [""] }] });
  }

  function removeDetailSection(index: number) {
    if (!draft) {
      return;
    }
    setDraft({ ...draft, details: draft.details.filter((_, sectionIndex) => sectionIndex !== index) });
  }

  return (
    <section className="registry-detail-pane">
      <div className="registry-detail-head">
        <div>
          <span className={item.builtin ? "registry-badge builtin" : "registry-badge"}>{item.builtin ? "内置" : "自定义"}</span>
          <h3>{item.name}</h3>
        </div>
        <label className="toggle-row">
          <input checked={draft.enabled} type="checkbox" onChange={(event) => onPatch(item, { enabled: event.target.checked })} />
          启用
        </label>
      </div>

      <div className="registry-edit-grid">
        <label>
          名称
          <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        </label>
        <label>
          描述
          <textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
        </label>
        <label>
          补充说明
          <textarea value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />
        </label>
      </div>

      <div className="registry-detail-sections">
        <div className="registry-section-title">
          <h4>具体内容</h4>
          <button className="secondary-button" type="button" onClick={addDetailSection}>
            新增分组
          </button>
        </div>
        {draft.details.map((section, index) => (
          <div className="registry-detail-section" key={`${section.title}-${index}`}>
            <input value={section.title} onChange={(event) => updateDetailSection(index, { title: event.target.value })} />
            <textarea
              value={section.items.join("\n")}
              onChange={(event) => updateDetailSection(index, { items: event.target.value.split("\n") })}
            />
            <button className="secondary-button" type="button" onClick={() => removeDetailSection(index)}>
              移除分组
            </button>
          </div>
        ))}
      </div>

      <div className="registry-actions">
        <button type="button" onClick={() => onPatch(item, { name: draft.name, description: draft.description, notes: draft.notes, details: draft.details })}>
          保存
        </button>
        <button className={item.builtin ? "secondary-button" : "danger-button"} type="button" onClick={() => onDelete(item)}>
          {item.builtin ? "禁用内置项" : "删除"}
        </button>
      </div>
    </section>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <h2 className="section-title">{title}</h2>;
}

function buildFileTree(entries: FileTreeEntry[]) {
  const nodes = new Map<string, FileTreeNode>();
  for (const entry of entries.slice(0, 220)) {
    nodes.set(entry.path, { ...entry, children: [] });
  }

  const roots: FileTreeNode[] = [];
  for (const node of nodes.values()) {
    const parent = nodes.get(parentPathFor(node.path));
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  sortFileTreeNodes(roots);
  return roots;
}

function parentPathFor(path: string) {
  const index = path.lastIndexOf("/");
  return index > 0 ? path.slice(0, index) : "";
}

function sortFileTreeNodes(nodes: FileTreeNode[]) {
  nodes.sort((left, right) => {
    if (left.kind !== right.kind) {
      return left.kind === "directory" ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });
  for (const node of nodes) {
    sortFileTreeNodes(node.children);
  }
}

function isHighLevelDirectoryInsight(directory: ProjectManualDirectory) {
  if (directory.depth <= 1) {
    return true;
  }

  const layerNames = new Set([
    "controller",
    "controllers",
    "service",
    "services",
    "dao",
    "repository",
    "repositories",
    "mapper",
    "mappers",
  ]);
  return directory.path
    .toLowerCase()
    .split("/")
    .some((part) => layerNames.has(part));
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function EvidenceSnippet({ evidence }: { evidence: RepoMapEvidence }) {
  return (
    <div className="snippet">
      <div>
        <code>{evidence.path}</code>
        <span>
          {evidence.collected_by_tool}
          {evidence.start_line && evidence.end_line ? ` · L${evidence.start_line}-L${evidence.end_line}` : ""}
        </span>
      </div>
      <p>{evidence.reason}</p>
      {evidence.excerpt ? <pre>{evidence.excerpt}</pre> : null}
    </div>
  );
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  return parseJsonResponse<T>(response);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<T>(response);
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return parseJsonResponse<T>(response);
}

async function deleteJson<T = unknown>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "DELETE" });
  return parseJsonResponse<T>(response);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? `请求失败，状态码：${response.status}`);
  }
  return payload as T;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function interpretationText(value: string | null | undefined) {
  return value?.trim() || "";
}

function intentLabel(intent: AskIntent) {
  const labels: Record<AskIntent, string> = {
    project_overview: "项目总览",
    module_explanation: "模块解释",
    file_explanation: "文件解释",
    call_chain: "调用链",
    api_usage: "接口",
    configuration: "配置",
    tech_stack: "技术栈",
  };
  return labels[intent];
}

function askResultText(result: AskModeResult) {
  const sections = [
    result.answer,
    result.related_files.length ? `相关文件：\n${result.related_files.slice(0, 8).map((path) => `- ${path}`).join("\n")}` : "",
    result.implementation_path.length ? `实现路径：\n${result.implementation_path.slice(0, 8).map((path) => `- ${path}`).join("\n")}` : "",
    result.key_code_notes.length ? `关键说明：\n${result.key_code_notes.slice(0, 5).map((note) => `- ${note}`).join("\n")}` : "",
    result.references.length
      ? `参考依据：\n${result.references
          .slice(0, 5)
          .map((item) => `- ${item.path}${item.start_line ? `:${item.start_line}` : ""} · ${item.source}`)
          .join("\n")}`
      : "参考依据：当前主要来自项目记忆；若代码中找不到明确证据，回答会保守说明。",
    result.warnings.length ? `不确定点：\n${result.warnings.slice(0, 4).map((warning) => `- ${warning}`).join("\n")}` : "",
  ];
  return sections.filter(Boolean).join("\n\n");
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
