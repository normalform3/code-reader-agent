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
  related_files: string[];
  api_candidates: string[];
  identification_basis: string;
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

type ProjectManualOverview = {
  project_name: string;
  project_type: string;
  one_liner: string;
  main_stack: string[];
  build_tools: string[];
  entrypoints: string[];
  maturity_observations: string[];
};

type ProjectManualRepoMapItem = {
  path: string;
  role: string;
  reason: string;
  importance: "core" | "supporting" | "skippable";
};

type ProjectManualCoreModule = {
  id: string;
  name: string;
  responsibility: string;
  related_files: string[];
  api_candidates: string[];
  identification_basis: string;
  confidence: number;
};

type ProjectManual = {
  title: string;
  overview: ProjectSummary | null;
  manual_overview: ProjectManualOverview | null;
  technology_stack: StackExplanation[];
  repo_map: ProjectManualRepoMapItem[];
  modules: ProjectManualModule[];
  core_modules: ProjectManualCoreModule[];
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
  active_skills?: ActiveSkillInfo[];
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
  fallback_reason?: string | null;
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

type ActiveSkillInfo = {
  name: string;
  confidence: number;
  reason: string;
};

type ProjectMemoryOverview = {
  positioning: string;
  description?: string;
  project_type?: string;
  tech_stack: string[];
  startup_commands: string[];
  entry_points?: string[];
  build_tools?: string[];
  config_files?: string[];
  external_dependencies?: string[];
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
  | "api_lookup"
  | "flow_trace"
  | "config_lookup"
  | "tech_stack"
  | "symbol_lookup"
  | "unknown"
  | "call_chain"
  | "api_usage"
  | "configuration";

type ResolvedQuery = {
  original_question: string;
  resolved_question: string;
  referenced_topic: string | null;
  referenced_files: string[];
  referenced_apis: string[];
  referenced_flows: string[];
};

type IntentResult = {
  intent: AskIntent;
  keywords: string[];
  possible_files: string[];
  possible_apis: string[];
  possible_symbols: string[];
  need_code_evidence: boolean;
};

type PlannedToolCall = {
  tool_name: string;
  args: Record<string, unknown>;
  purpose: string;
};

type ToolPlan = {
  need_tools: boolean;
  reason: string;
  tool_calls: PlannedToolCall[];
};

type InvestigationPlanItem = {
  id: string;
  title: string;
  evidence_goal: string;
  status: "pending" | "satisfied" | "missing";
};

type InvestigationReview = {
  satisfied_goal_ids: string[];
  missing_evidence: string[];
  needs_more_evidence: boolean;
  stop_reason: string;
  next_step: string | null;
};

type InvestigationEvidence = EvidenceRef;

type InvestigationFlowStep = {
  source: string;
  target: string;
  relation: string;
  status: "confirmed" | "unconfirmed";
  evidence: InvestigationEvidence[];
};

type InvestigationFinding = {
  title: string;
  statement: string;
  status: "confirmed" | "unconfirmed";
  confidence: number;
  evidence: InvestigationEvidence[];
  missing_evidence: string[];
};

type InvestigationResult = {
  goal: string;
  status: "complete" | "partial";
  plan: InvestigationPlanItem[];
  flow_steps: InvestigationFlowStep[];
  findings: InvestigationFinding[];
  review: InvestigationReview;
};

type CodeEvidence = {
  source: "memory" | "tool";
  file_path: string | null;
  symbol: string | null;
  api: string | null;
  content_summary: string;
  code_snippet: string | null;
  relevance_reason: string;
};

type ContextPack = {
  user_question: string;
  resolved_question: string;
  project_context: string;
  session_context: string;
  code_evidence: CodeEvidence[];
  context_text: string;
  truncated: boolean;
};

type QueryHint = {
  keyword: string;
  reason: string;
  priority: number;
};

type RoutedSkillInfo = {
  name: string;
  confidence: number;
  reason: string;
  signals: string[];
};

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
  resolved_query: ResolvedQuery | null;
  intent_result: IntentResult | null;
  investigation: InvestigationResult | null;
  tool_plan: ToolPlan | null;
  context_pack: ContextPack | null;
  routed_skills: RoutedSkillInfo[];
  query_hints: QueryHint[];
  code_evidence: CodeEvidence[];
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
  used_llm: boolean;
  fallback_used: boolean;
  fallback_reason: string | null;
  llm_model: string | null;
};

type AskModeRequest = {
  project_path: string;
  question: string;
  conversation_id?: string | null;
  session_memory: SessionMemory | null;
};

type AskConversationMessage = {
  id: string;
  role: "user" | "assistant";
  body: string;
  meta: string | null;
  created_at: string;
};

type AskConversation = {
  id: string;
  project_id: string;
  project_path: string;
  title: string;
  messages: AskConversationMessage[];
  session_memory: SessionMemory;
  last_question: string | null;
  created_at: string;
  updated_at: string;
};

type AskStreamEvent =
  | { type: "trace"; node?: string; event?: TraceEvent }
  | { type: "goal_plan"; node?: string; event?: InvestigationPlanItem[] }
  | { type: "evidence_review"; node?: string; event?: InvestigationReview }
  | { type: "replan"; node?: string; event?: { reason?: string } }
  | { type: "tool_plan"; node?: string; event?: ToolPlan }
  | { type: "tool_result"; node?: string; event?: AskModeResult["tool_calls"][number] }
  | { type: "answer"; node?: string; event?: { answer?: string }; answer?: string }
  | { type: "final"; event?: AskModeResult; conversation?: AskConversation }
  | { type: "error"; error?: string };

type AgentRunStreamStep = {
  title?: string;
  summary?: string;
  status?: "success" | "error";
  tool_name?: string | null;
};

type AgentRunStreamEvent =
  | { type: "step"; node?: string; event?: AgentRunStreamStep }
  | { type: "trace"; node?: string; event?: TraceEvent }
  | { type: "final"; event?: Interpretation }
  | { type: "error"; error?: string };

type ModelSettingsStatus = {
  provider: "bailian";
  model: string;
  api_key_env: string;
  base_url_env: string;
  api_key_configured: boolean;
  base_url_configured: boolean;
  litellm_installed: boolean;
  langgraph_installed: boolean;
  updated_at: string;
};

type ModelConnectionTestResult = {
  ok: boolean;
  provider: "bailian";
  model: string;
  message: string;
  response_preview: string;
  missing_environment: string[];
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
  streaming?: boolean;
  traceEvents?: TraceEvent[];
};
type FileTreeNode = FileTreeEntry & {
  children: FileTreeNode[];
};

const DEFAULT_QUESTION = "请先为这个仓库生成项目说明书：这个项目是什么、主要做什么？用了什么技术栈和构建工具？有哪些关键目录？请给出代码库总览和关键目录导航。";

function App() {
  const [registryModal, setRegistryModal] = useState<RegistryKind | null>(null);
  const [modelSettingsOpen, setModelSettingsOpen] = useState(false);
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [askExpanded, setAskExpanded] = useState(false);
  const [sidebarView, setSidebarView] = useState<SidebarView>("history");
  const [projectPath, setProjectPath] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [githubImport, setGithubImport] = useState<GitHubImportResult | null>(null);
  const [question, setQuestion] = useState("");
  const [askMessages, setAskMessages] = useState<AskMessage[]>([]);
  const [askConversations, setAskConversations] = useState<AskConversation[]>([]);
  const [activeAskConversationId, setActiveAskConversationId] = useState<string | null>(null);
  const [repoMap, setRepoMap] = useState<RepoMap | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [askResult, setAskResult] = useState<AskModeResult | null>(null);
  const [askSessionMemory, setAskSessionMemory] = useState<SessionMemory | null>(null);
  const [projectManual, setProjectManual] = useState<ProjectManual | null>(null);
  const [manualTraceEvents, setManualTraceEvents] = useState<TraceEvent[]>([]);
  const [manualTraceStreaming, setManualTraceStreaming] = useState(false);
  const [status, setStatus] = useState<Status>("empty");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshSessions();
  }, []);

  const activeSession = sessions.find((item) => item.id === activeSessionId) ?? null;
  const activeAskConversation = askConversations.find((item) => item.id === activeAskConversationId) ?? null;

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

  async function loadAskConversations(projectId: string, options: { ensureConversation?: boolean; preferredConversationId?: string | null } = {}) {
    const ensureConversation = options.ensureConversation ?? true;
    let conversations = await getJson<AskConversation[]>(`/api/projects/${projectId}/ask-conversations`);
    if (conversations.length === 0 && ensureConversation) {
      const created = await postJson<AskConversation>(`/api/projects/${projectId}/ask-conversations`, { title: "新对话" });
      conversations = [created];
    }
    setAskConversations(conversations);
    const selected =
      conversations.find((item) => item.id === options.preferredConversationId) ??
      conversations[0] ??
      null;
    setActiveAskConversationId(selected?.id ?? null);
    setAskMessages(selected ? messagesFromConversation(selected) : []);
    setAskSessionMemory(selected?.session_memory ?? null);
    setAskResult(null);
    return selected;
  }

  async function handleNewAskConversation() {
    if (!activeSessionId) {
      return;
    }
    const created = await postJson<AskConversation>(`/api/projects/${activeSessionId}/ask-conversations`, { title: "新对话" });
    setAskConversations((current) => [created, ...current]);
    setActiveAskConversationId(created.id);
    setAskMessages([]);
    setAskSessionMemory(created.session_memory);
    setAskResult(null);
  }

  function handleSelectAskConversation(conversationId: string) {
    const conversation = askConversations.find((item) => item.id === conversationId);
    if (!conversation) {
      return;
    }
    setActiveAskConversationId(conversation.id);
    setAskMessages(messagesFromConversation(conversation));
    setAskSessionMemory(conversation.session_memory);
    setAskResult(null);
  }

  async function analyzeProject(
    nextProjectPath: string,
    nextQuestion = DEFAULT_QUESTION,
    onStreamEvent?: (event: AgentRunStreamEvent) => void,
  ) {
    setStatus("loading");
    setError(null);
    setInterpretation(null);
    setAskResult(null);
    setProjectPath(nextProjectPath);

    const [repoMapResult, interpretationResult] = await Promise.all([
      postJson<RepoMap>("/api/projects/repo-map", { project_path: nextProjectPath }),
      postAgentRunStream({
        project_path: nextProjectPath,
        question: nextQuestion,
      }, onStreamEvent),
    ]);
    setRepoMap(repoMapResult);
    setInterpretation(interpretationResult);
    setProjectManual(interpretationResult.project_manual ?? null);
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
    setAskConversations([]);
    setActiveAskConversationId(null);
    setProjectManual(null);
    setAskMessages([]);
    setManualTraceEvents([]);
    setManualTraceStreaming(false);
    setGithubImport(null);

    try {
      const importedProject = await postJson<GitHubImportResult>("/api/projects/import-github", {
        github_url: githubUrl.trim(),
      });
      setGithubImport(importedProject);
      const analysisQuestion = question.trim() || DEFAULT_QUESTION;
      setManualTraceEvents([]);
      setManualTraceStreaming(true);
      const { repoMapResult, interpretationResult } = await analyzeProject(importedProject.project_path, analysisQuestion, (event) => {
        updateManualTraceFromStream(event);
      });
      setManualTraceEvents((current) => (interpretationResult.trace_events?.length ? interpretationResult.trace_events : current));
      setManualTraceStreaming(false);
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
      await loadAskConversations(session.id);
      await refreshSessions();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "导入或分析失败，请检查 GitHub 链接和本地 API。";
      setError(message);
      setStatus("error");
      setManualTraceStreaming(false);
    }
  }

  async function handleSelectSession(session: ProjectSession) {
    setActiveSessionId(session.id);
    setGithubImport(null);
    setGithubUrl(session.github_url ?? "");
    setQuestion("");
    setAskMessages([]);
    setAskSessionMemory(null);
    setAskConversations([]);
    setActiveAskConversationId(null);
    setManualTraceEvents([]);
    setManualTraceStreaming(true);
    setSidebarView("files");
    try {
      const { interpretationResult } = await analyzeProject(session.project_path, DEFAULT_QUESTION, (event) => {
        updateManualTraceFromStream(event);
      });
      setManualTraceEvents((current) => (interpretationResult.trace_events?.length ? interpretationResult.trace_events : current));
      setManualTraceStreaming(false);
      await loadAskConversations(session.id);
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
      setManualTraceStreaming(false);
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
      setAskConversations([]);
      setActiveAskConversationId(null);
      setProjectManual(null);
      setAskMessages([]);
      setManualTraceEvents([]);
      setManualTraceStreaming(false);
      setProjectPath("");
      setStatus("empty");
    }
    await refreshSessions();
  }

  async function handleAsk() {
    if (!projectPath.trim()) {
      return;
    }
    const askedQuestion = question.trim();
    if (!askedQuestion) {
      return;
    }
    setStatus("loading");
    setError(null);
    let conversation = activeAskConversation;
    if (!conversation && activeSessionId) {
      conversation = await loadAskConversations(activeSessionId);
    }
    const assistantMessageId = `${Date.now()}-assistant-stream`;
    setAskMessages((current) => [
      ...current,
      {
        id: `${Date.now()}-user`,
        role: "user",
        body: askedQuestion,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        body: "Agent 正在分析问题并收集证据...",
        meta: "Ask · streaming",
        streaming: true,
        traceEvents: [],
      },
    ]);
    try {
      const result = await postAskStream(
        {
          project_path: projectPath.trim(),
          question: askedQuestion,
          conversation_id: conversation?.id ?? null,
          session_memory: conversation ? null : askSessionMemory,
        },
        (event) => {
          if (event.type === "final" && event.conversation) {
            setAskConversations((current) => upsertAskConversation(current, event.conversation as AskConversation));
            setActiveAskConversationId(event.conversation.id);
            setAskSessionMemory(event.conversation.session_memory);
          }
          setAskMessages((current) =>
            current.map((message) => {
              if (message.id !== assistantMessageId) {
                return message;
              }
              if (event.type === "trace" && event.event) {
                return {
                  ...message,
                  body: message.body || "Agent 正在分析问题并收集证据...",
                  traceEvents: [...(message.traceEvents ?? []), event.event],
                };
              }
              if (event.type === "goal_plan" && event.event) {
                return {
                  ...message,
                  body: `Agent 已制定 ${event.event.length} 项可验证调查目标，正在收集流程证据...`,
                };
              }
              if (event.type === "evidence_review" && event.event) {
                return {
                  ...message,
                  body: event.event.needs_more_evidence
                    ? "Agent 发现关键证据缺口，正在重新规划调查..."
                    : "Agent 已完成证据审查，正在生成调查报告...",
                };
              }
              if (event.type === "replan") {
                return {
                  ...message,
                  body: event.event?.reason ?? "Agent 正在围绕证据缺口重新规划...",
                };
              }
              if (event.type === "tool_plan") {
                return {
                  ...message,
                  body: "Agent 已完成工具计划，正在读取只读证据...",
                };
              }
              if (event.type === "tool_result" && event.event) {
                const traceEvent: TraceEvent = {
                  index: (message.traceEvents?.length ?? 0) + 1,
                  stage: "Tool Executor",
                  title: event.event.tool_name,
                  summary: event.event.output_summary,
                  status: event.event.status,
                  tool_name: event.event.tool_name,
                };
                return {
                  ...message,
                  body: "Agent 正在整理工具结果和上下文...",
                  traceEvents: [...(message.traceEvents ?? []), traceEvent],
                };
              }
              if (event.type === "answer" && event.answer) {
                return {
                  ...message,
                  body: event.answer,
                };
              }
              return message;
            }),
          );
        },
      );
      setAskResult(result);
      setAskSessionMemory(result.session_memory);
      setAskMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                body: askResultText(result),
                meta: `Ask · ${intentLabel(result.intent)} · ${result.used_llm ? result.llm_model ?? "LLM" : "规则降级"}`,
                streaming: false,
                traceEvents: result.trace_events,
              }
            : message,
        ),
      );
      setStatus("ready");
      if (activeSessionId) {
        await patchJson<ProjectSession>(`/api/projects/history/${activeSessionId}`, {
          status: "ready",
          last_question: askedQuestion,
          last_error: null,
        });
        await refreshSessions();
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "提问失败，请检查本地 API 是否已启动。";
      setError(message);
      setAskMessages((current) =>
        current.map((item) =>
          item.id === assistantMessageId
            ? {
                ...item,
                body: message,
                meta: "Ask · error",
                streaming: false,
              }
            : item,
        ),
      );
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

  function updateManualTraceFromStream(event: AgentRunStreamEvent) {
    setManualTraceEvents((current) => {
      if (event.type === "trace" && event.event) {
        return [...current, event.event];
      }
      if (event.type === "step" && event.event) {
        const traceEvent: TraceEvent = {
          index: current.length + 1,
          stage: event.node ?? "Agent Runtime",
          title: event.event.title ?? event.node ?? "Agent step",
          summary: event.event.summary ?? "Agent 正在生成项目说明书。",
          status: event.event.status ?? "success",
          tool_name: event.event.tool_name ?? null,
        };
        return [...current, traceEvent];
      }
      if (event.type === "error") {
        const traceEvent: TraceEvent = {
          index: current.length + 1,
          stage: "Agent Runtime",
          title: "Stream error",
          summary: event.error ?? "项目说明书生成失败。",
          status: "error",
          tool_name: null,
        };
        setManualTraceStreaming(false);
        return [...current, traceEvent];
      }
      return current;
    });
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
        onOpenModelSettings={() => setModelSettingsOpen(true)}
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
        activeAskConversationId={activeAskConversationId}
        askExpanded={askExpanded}
        askConversations={askConversations}
        askMessages={askMessages}
        askResult={askResult}
        error={error}
        githubImport={githubImport}
        interpretation={interpretation}
        manualTraceEvents={manualTraceEvents}
        manualTraceStreaming={manualTraceStreaming}
        onAsk={handleAsk}
        onNewAskConversation={handleNewAskConversation}
        onSelectAskConversation={handleSelectAskConversation}
        onSetQuestion={setQuestion}
        onToggleAskExpanded={() => setAskExpanded((current) => !current)}
        projectManual={projectManual}
        question={question}
        repoMap={repoMap}
        status={status}
      />

      {registryModal ? <RegistryModal kind={registryModal} onClose={() => setRegistryModal(null)} /> : null}
      {modelSettingsOpen ? <ModelSettingsModal onClose={() => setModelSettingsOpen(false)} /> : null}
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
  onOpenModelSettings,
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
  onOpenModelSettings: () => void;
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
        <button className="nav-button" type="button" onClick={onOpenModelSettings}>
          模型设置
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
  activeAskConversationId,
  askExpanded,
  askConversations,
  askMessages,
  askResult,
  error,
  githubImport,
  interpretation,
  manualTraceEvents,
  manualTraceStreaming,
  onAsk,
  onNewAskConversation,
  onSelectAskConversation,
  onSetQuestion,
  onToggleAskExpanded,
  projectManual,
  question,
  repoMap,
  status,
}: {
  activeSession: ProjectSession | null;
  activeAskConversationId: string | null;
  askExpanded: boolean;
  askConversations: AskConversation[];
  askMessages: AskMessage[];
  askResult: AskModeResult | null;
  error: string | null;
  githubImport: GitHubImportResult | null;
  interpretation: Interpretation | null;
  manualTraceEvents: TraceEvent[];
  manualTraceStreaming: boolean;
  onAsk: () => void;
  onNewAskConversation: () => void;
  onSelectAskConversation: (conversationId: string) => void;
  onSetQuestion: (question: string) => void;
  onToggleAskExpanded: () => void;
  projectManual: ProjectManual | null;
  question: string;
  repoMap: RepoMap | null;
  status: Status;
}) {
  const statusLabel: Record<Status, string> = {
    empty: "未扫描",
    importing: "下载中",
    loading: "分析中",
    ready: "已完成",
    error: "出错",
  };
  const manualOverview = projectManual?.manual_overview ?? null;
  const summaryOverview = projectManual?.overview ?? repoMap?.project_summary ?? null;
  const mainStack = manualOverview?.main_stack.length
    ? manualOverview.main_stack
    : projectManual?.technology_stack.length
      ? projectManual.technology_stack.map((item) => item.name)
      : repoMap?.detected_stack.map((item) => item.name) ?? [];
  const buildTools = manualOverview?.build_tools.length
    ? manualOverview.build_tools
    : [repoMap?.package_manager, repoMap?.java_build_tool].filter(isPresent);
  const entrypoints = manualOverview?.entrypoints.length
    ? manualOverview.entrypoints
    : projectManual?.entrypoints.length
      ? projectManual.entrypoints.map((item) => item.path)
      : repoMap?.entrypoints.filter((item) => item.exists).map((item) => item.path) ?? [];
  const interpretationFallbackReason =
    interpretation?.fallback_reason ?? (interpretation?.fallback_used ? interpretation.warnings?.[0] ?? null : null);

  return (
    <section className={askExpanded ? "workspace-shell ask-expanded" : "workspace-shell"}>
      {!askExpanded ? <section className="map-panel">
        <header className="workspace-header">
          <div>
            <p className="kicker">项目说明书</p>
            <h2>{repoMap?.project_name ?? activeSession?.title ?? "输入公开 GitHub 仓库链接"}</h2>
            <span>{githubImport?.github_url ?? activeSession?.github_url ?? "像会话一样保存每个项目的分析历史。"}</span>
          </div>
          <div className="status-pill" data-status={status}>
            {statusLabel[status]}
          </div>
        </header>

        <ManualTracePanel events={manualTraceEvents} streaming={manualTraceStreaming} />

        {error ? <div className="error-box">{error}</div> : null}

        <section className="overview-panel">
          <div className="summary-card">
            <div className="detail-heading">
              <div>
                <p className="kicker">代码库总览</p>
                <h3>{manualOverview?.one_liner ?? summaryOverview?.one_liner ?? "扫描完成后生成项目概述"}</h3>
              </div>
              {summaryOverview ? <span>{Math.round(summaryOverview.confidence * 100)}% 置信度</span> : null}
            </div>
            <div className="summary-grid">
              <div>
                <strong>这个项目是什么</strong>
                <p>{summaryOverview?.audience ?? manualOverview?.project_type ?? "等待 README、配置和入口文件证据。"}</p>
              </div>
              <div>
                <strong>主要做什么</strong>
                <p>{summaryOverview?.problem ?? manualOverview?.one_liner ?? "证据不足时会明确提示低置信度。"}</p>
              </div>
            </div>
            <div className="manual-facts">
              <div>
                <span>项目类型</span>
                <strong>{manualOverview?.project_type || "待确认项目"}</strong>
              </div>
              <div>
                <span>主要技术栈</span>
                <strong>{mainStack.slice(0, 6).join(" / ") || "未识别"}</strong>
              </div>
              <div>
                <span>构建工具</span>
                <strong>{buildTools.slice(0, 4).join(" / ") || "未识别"}</strong>
              </div>
              <div>
                <span>入口候选</span>
                <strong>{entrypoints.slice(0, 3).join(" / ") || "暂无"}</strong>
              </div>
            </div>
            {manualOverview?.maturity_observations.length ? (
              <div className="manual-tags">
                {manualOverview.maturity_observations.slice(0, 6).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            ) : null}
            {interpretationFallbackReason ? (
              <span className="warning-note">LLM 降级原因：{interpretationFallbackReason}</span>
            ) : null}
          </div>

          <ProjectManualCard manual={projectManual} />
        </section>
      </section> : null}

      <button
        aria-label={askExpanded ? "显示项目说明书" : "隐藏项目说明书并展开 Ask"}
        className="ask-expand-toggle"
        onClick={onToggleAskExpanded}
        title={askExpanded ? "显示项目说明书" : "展开 Ask"}
        type="button"
      >
        {askExpanded ? ">" : "<"}
      </button>

      <AgentPanel
        activeAskConversationId={activeAskConversationId}
        askConversations={askConversations}
        askMessages={askMessages}
        askResult={askResult}
        interpretation={interpretation}
        onAsk={onAsk}
        onNewAskConversation={onNewAskConversation}
        onSelectAskConversation={onSelectAskConversation}
        onSetQuestion={onSetQuestion}
        question={question}
        repoMap={repoMap}
        status={status}
      />
    </section>
  );
}

function ManualTracePanel({ events, streaming }: { events: TraceEvent[]; streaming: boolean }) {
  const [open, setOpen] = useState(streaming);

  useEffect(() => {
    if (streaming) {
      setOpen(true);
    }
  }, [streaming]);

  if (!streaming && events.length === 0) {
    return null;
  }

  const latest = events[events.length - 1];
  return (
    <details className="manual-trace-panel" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <div>
          <p className="kicker">生成流程</p>
          <strong>{latest?.summary ?? "Agent 正在创建项目说明书分析任务..."}</strong>
        </div>
        <span>{streaming ? "流式生成中" : `${events.length} 步`}</span>
      </summary>
      <div className="manual-trace-list">
        {events.length > 0 ? (
          events.map((event) => (
            <div className="manual-trace-row" data-status={event.status} key={`${event.index}-${event.stage}-${event.title}`}>
              <span>{event.stage}</span>
              <strong>{event.title}</strong>
              <small>{event.summary}</small>
            </div>
          ))
        ) : (
          <span className="muted">等待后端返回扫描、Repo Map 和 Report Writer 进度。</span>
        )}
        {streaming ? <em>持续接收 Agent 进度...</em> : null}
      </div>
    </details>
  );
}

function AgentPanel({
  activeAskConversationId,
  askConversations,
  askMessages,
  askResult,
  interpretation,
  onAsk,
  onNewAskConversation,
  onSelectAskConversation,
  onSetQuestion,
  question,
  repoMap,
  status,
}: {
  activeAskConversationId: string | null;
  askConversations: AskConversation[];
  askMessages: AskMessage[];
  askResult: AskModeResult | null;
  interpretation: Interpretation | null;
  onAsk: () => void;
  onNewAskConversation: () => void;
  onSelectAskConversation: (conversationId: string) => void;
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
  const askFallbackReason = askResult?.fallback_reason ?? (askResult?.fallback_used ? askResult.warnings[0] ?? null : null);
  const interpretationFallbackReason =
    interpretation?.fallback_reason ?? (interpretation?.fallback_used ? interpretation.warnings?.[0] ?? null : null);
  return (
    <aside className="agent-panel">
      <header className="ask-header">
        <div>
          <p className="kicker">Ask</p>
          <h3>CodeReader Copilot</h3>
        </div>
        <span className="ask-status">
          {askResult
            ? `Ask · ${askResult.used_llm ? askResult.llm_model ?? "LLM" : "规则降级"}`
            : `${interpretation?.used_llm ? "LLM" : "规则"} · ${interpretation?.task_id ?? "待命"}`}
        </span>
      </header>

      <div className="ask-conversation-bar">
        <select
          aria-label="选择 Ask 对话"
          disabled={!askConversations.length}
          onChange={(event) => onSelectAskConversation(event.target.value)}
          value={activeAskConversationId ?? ""}
        >
          {askConversations.length ? (
            askConversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))
          ) : (
            <option value="">暂无对话</option>
          )}
        </select>
        <button disabled={!repoMap || status === "importing" || status === "loading"} onClick={onNewAskConversation} type="button">
          新对话
        </button>
      </div>

      <div className="ask-scroll-area">
        <div className="ask-thread">
          {askMessages.length > 0 ? (
            askMessages.map((message) => (
              <article className={`ask-message ${message.role}`} key={message.id}>
                <span>{message.role === "user" ? "你" : message.meta ?? "Agent"}</span>
                <p>{message.body}</p>
                {message.traceEvents?.length ? (
                  <div className="ask-message-trace">
                    {message.traceEvents.slice(-6).map((event) => (
                      <div className="ask-message-trace-row" data-status={event.status} key={`${message.id}-${event.index}-${event.stage}-${event.title}`}>
                        <strong>{event.stage}</strong>
                        <small>{event.title}</small>
                      </div>
                    ))}
                    {message.streaming ? <em>持续接收 Agent 进度...</em> : null}
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <article className="ask-message assistant">
              <span>Agent</span>
              <p>{latestAnswer}</p>
            </article>
          )}
          {askFallbackReason ? <span className="warning-note">Ask 降级原因：{askFallbackReason}</span> : null}
          {!askFallbackReason && interpretationFallbackReason ? (
            <span className="warning-note">项目说明书降级原因：{interpretationFallbackReason}</span>
          ) : null}
        </div>

        {askResult?.investigation ? <InvestigationCard investigation={askResult.investigation} /> : null}

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
              {askResult?.resolved_query ? <code>Resolved</code> : null}
              {askResult?.context_pack ? <code>{askResult.context_pack.truncated ? "Context trimmed" : "Context Pack"}</code> : null}
              {askResult?.tool_calls.slice(0, 4).map((call, index) => (
                <code key={`${call.tool_name}-${index}`}>{call.tool_name}</code>
              ))}
              {askResult?.routed_skills.slice(0, 4).map((skill) => (
                <code key={`ask-${skill.name}`}>{skill.name}</code>
              ))}
              {(interpretation?.active_skills?.length ? interpretation.active_skills.map((skill) => skill.name) : interpretation?.selected_skills)?.map((skill) => <code key={skill}>{skill}</code>) ?? null}
              {askResult ? <span className="muted">{askResult.code_evidence.length || askResult.references.length} 条 Ask evidence · {askResult.session_memory.turns.length} 轮记忆</span> : null}
              {interpretation?.context_snapshot ? (
                <span className="muted">
                  {interpretation.context_snapshot.evidence_count} 条 evidence · {interpretation.context_snapshot.read_files.length} 个已读取文件
                </span>
              ) : null}
            </div>
            {askResult?.resolved_query ? (
              <p className="context-note">
                {askResult.resolved_query.resolved_question}
              </p>
            ) : null}
            {askResult?.tool_plan ? (
              <p className="context-note">
                {askResult.tool_plan.reason}
              </p>
            ) : null}
            {interpretation?.active_skills?.length ? (
              <div className="step-list">
                {interpretation.active_skills.slice(0, 6).map((skill) => (
                  <div className="step-row" data-status="success" key={skill.name}>
                    <span>{Math.round(skill.confidence * 100)}%</span>
                    <strong>{skill.name}</strong>
                    <small>{skill.reason}</small>
                  </div>
                ))}
              </div>
            ) : null}
            {askResult?.query_hints?.length ? (
              <p className="context-note">
                Routed skills: {askResult.routed_skills.slice(0, 5).map((skill) => skill.name).join(", ") || "none"} · Skill hints: {askResult.query_hints.slice(0, 6).map((hint) => hint.keyword).join(", ")}
              </p>
            ) : null}
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

function InvestigationCard({ investigation }: { investigation: InvestigationResult }) {
  return (
    <section className="investigation-card" data-status={investigation.status}>
      <header>
        <div>
          <p className="kicker">自主调查</p>
          <strong>{investigation.status === "complete" ? "证据闭环完成" : "部分证据调查"}</strong>
        </div>
        <span>{investigation.plan.filter((item) => item.status === "satisfied").length}/{investigation.plan.length} 目标</span>
      </header>
      <p>{investigation.goal}</p>
      <ol className="investigation-plan">
        {investigation.plan.map((item) => (
          <li data-status={item.status} key={item.id}>
            <strong>{item.title}</strong>
            <small>{item.status === "satisfied" ? "已验证" : "待确认"}</small>
          </li>
        ))}
      </ol>
      {investigation.flow_steps.length ? (
        <div className="investigation-flow">
          {investigation.flow_steps.map((step) => (
            <div data-status={step.status} key={`${step.source}-${step.target}`}>
              <strong>{step.source} → {step.target}</strong>
              <small>{step.status === "confirmed" ? step.relation : `待确认：${step.relation}`}</small>
              {step.evidence.length ? <code>{step.evidence.map((item) => item.path).join(" · ")}</code> : null}
            </div>
          ))}
        </div>
      ) : null}
      {investigation.review.missing_evidence.length ? (
        <p className="warning-note">未确认断点：{investigation.review.missing_evidence.join("；")}</p>
      ) : null}
    </section>
  );
}

function ModelSettingsModal({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<ModelSettingsStatus | null>(null);
  const [modelDraft, setModelDraft] = useState("glm-5.1");
  const [status, setStatus] = useState<"loading" | "ready" | "saving" | "testing" | "error">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ModelConnectionTestResult | null>(null);

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings() {
    setStatus("loading");
    setMessage(null);
    try {
      const result = await getJson<ModelSettingsStatus>("/api/model-settings");
      setSettings(result);
      setModelDraft(result.model);
      setStatus("ready");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "读取模型设置失败。");
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("saving");
    setMessage(null);
    setTestResult(null);
    try {
      const result = await postJson<ModelSettingsStatus>("/api/model-settings", { model: modelDraft.trim() });
      setSettings(result);
      setModelDraft(result.model);
      setStatus("ready");
      setMessage("模型设置已保存。");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "保存模型设置失败。");
    }
  }

  async function testConnection() {
    setStatus("testing");
    setMessage(null);
    try {
      const result = await postJson<ModelConnectionTestResult>("/api/model-settings/test", {});
      setTestResult(result);
      setStatus("ready");
      setMessage(result.ok ? "百炼模型连通正常。" : result.message);
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "测试模型连通失败。");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="settings-modal" role="dialog">
        <header className="registry-modal-header">
          <div>
            <p className="kicker">Model Settings</p>
            <h2>百炼模型设置</h2>
            <span>当前只支持百炼 OpenAI-compatible 接口；密钥和 Base URL 从环境变量读取。</span>
          </div>
          <button className="secondary-button" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="settings-modal-body">
          <form className="settings-form" onSubmit={saveSettings}>
            <label htmlFor="model-name">模型名称</label>
            <input id="model-name" value={modelDraft} onChange={(event) => setModelDraft(event.target.value)} placeholder="glm-5.1" />
            <div className="settings-actions">
              <button type="submit" disabled={status === "saving" || !modelDraft.trim()}>
                {status === "saving" ? "保存中..." : "保存设置"}
              </button>
              <button className="secondary-button" type="button" onClick={testConnection} disabled={status === "testing" || status === "loading"}>
                {status === "testing" ? "测试中..." : "测试连通"}
              </button>
            </div>
          </form>

          <div className="settings-grid">
            <StatusTile label="Provider" value="百炼" ok />
            <StatusTile label="LiteLLM" value={settings?.litellm_installed ? "已安装" : "未安装"} ok={Boolean(settings?.litellm_installed)} />
            <StatusTile label="LangGraph" value={settings?.langgraph_installed ? "已安装" : "未安装，使用顺序 fallback"} ok={Boolean(settings?.langgraph_installed)} />
            <StatusTile label={settings?.api_key_env ?? "DASHSCOPE_API_KEY"} value={settings?.api_key_configured ? "已配置" : "未配置"} ok={Boolean(settings?.api_key_configured)} />
            <StatusTile label={settings?.base_url_env ?? "DASHSCOPE_BASE_URL"} value={settings?.base_url_configured ? "已配置" : "未配置"} ok={Boolean(settings?.base_url_configured)} />
            <StatusTile label="当前模型" value={settings?.model ?? modelDraft} ok={Boolean(settings?.model ?? modelDraft)} />
          </div>

          {message ? <div className={status === "error" || testResult?.ok === false ? "error-box" : "success-box"}>{message}</div> : null}
          {testResult ? (
            <div className="settings-result">
              <strong>{testResult.ok ? "连通成功" : "连通失败"}</strong>
              <p>{testResult.message}</p>
              {testResult.response_preview ? <code>{testResult.response_preview}</code> : null}
              {testResult.missing_environment.length ? <span>缺少：{testResult.missing_environment.join(", ")}</span> : null}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function StatusTile({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="status-tile" data-ok={ok}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProjectManualCard({ manual }: { manual: ProjectManual | null }) {
  if (!manual) {
    return (
      <div className="manual-card">
        <div className="detail-heading">
          <div>
            <p className="kicker">项目说明书</p>
            <h3>等待首次扫描生成说明书</h3>
          </div>
        </div>
        <p className="muted">导入项目后，Agent 会先生成代码库总览和关键目录导航。</p>
      </div>
    );
  }

  const manualRepoMap = manual.repo_map ?? [];
  const manualKeyDirectories = manual.key_directories ?? [];
  const repoMapItems =
    manualRepoMap.length > 0
      ? manualRepoMap
      : manualKeyDirectories.slice(0, 10).map((directory) => ({
          path: directory.path,
          role: directory.role,
          reason: directory.reason,
          importance: directory.importance,
        }));

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
        <ManualColumn title="关键目录 / Repo Map" empty="暂无关键目录">
          {repoMapItems.slice(0, 10).map((item) => (
            <div className="manual-row" key={item.path}>
              <code>{item.path}</code>
              <span>
                {item.role} · {item.importance}
              </span>
              <p>{item.reason}</p>
            </div>
          ))}
        </ManualColumn>
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

function isModuleLevelDirectoryInsight(directory: ProjectManualDirectory) {
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

function isPresent<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined && value !== "";
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

async function postAskStream(body: AskModeRequest, onEvent: (event: AskStreamEvent) => void): Promise<AskModeResult> {
  const response = await fetch(`${API_BASE_URL}/api/agent/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    return parseJsonResponse<AskModeResult>(response);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: AskModeResult | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseSseFrame<AskStreamEvent>(frame);
        if (!event) {
          continue;
        }
        const normalized = normalizeAskStreamEvent(event);
        if (normalized.type === "error") {
          throw new Error(normalized.error ?? "Ask stream failed.");
        }
        if (normalized.type === "final" && normalized.event) {
          finalResult = normalized.event;
        }
        onEvent(normalized);
      }
    }
    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const event = parseSseFrame<AskStreamEvent>(buffer);
    if (event) {
      const normalized = normalizeAskStreamEvent(event);
      if (normalized.type === "error") {
        throw new Error(normalized.error ?? "Ask stream failed.");
      }
      if (normalized.type === "final" && normalized.event) {
        finalResult = normalized.event;
      }
      onEvent(normalized);
    }
  }

  if (!finalResult) {
    throw new Error("Ask stream ended before final result.");
  }
  return finalResult;
}

async function postAgentRunStream(
  body: { project_path: string; question: string },
  onEvent?: (event: AgentRunStreamEvent) => void,
): Promise<Interpretation> {
  const response = await fetch(`${API_BASE_URL}/api/agent/run/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    return parseJsonResponse<Interpretation>(response);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: Interpretation | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseSseFrame<AgentRunStreamEvent>(frame);
        if (!event) {
          continue;
        }
        if (event.type === "error") {
          onEvent?.(event);
          throw new Error(event.error ?? "Agent run stream failed.");
        }
        if (event.type === "final" && event.event) {
          finalResult = event.event;
        }
        onEvent?.(event);
      }
    }
    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const event = parseSseFrame<AgentRunStreamEvent>(buffer);
    if (event) {
      if (event.type === "error") {
        onEvent?.(event);
        throw new Error(event.error ?? "Agent run stream failed.");
      }
      if (event.type === "final" && event.event) {
        finalResult = event.event;
      }
      onEvent?.(event);
    }
  }

  if (!finalResult) {
    throw new Error("Agent run stream ended before final result.");
  }
  return finalResult;
}

function parseSseFrame<T>(frame: string): T | null {
  const dataLines = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (!dataLines.length) {
    return null;
  }
  try {
    return JSON.parse(dataLines.join("\n")) as T;
  } catch {
    return null;
  }
}

function normalizeAskStreamEvent(event: AskStreamEvent): AskStreamEvent {
  if (event.type === "answer" && !event.answer && event.event?.answer) {
    return { ...event, answer: event.event.answer };
  }
  return event;
}

function messagesFromConversation(conversation: AskConversation): AskMessage[] {
  return conversation.messages.map((message) => ({
    id: message.id,
    role: message.role,
    body: message.body,
    meta: message.meta ?? undefined,
  }));
}

function upsertAskConversation(items: AskConversation[], conversation: AskConversation): AskConversation[] {
  const exists = items.some((item) => item.id === conversation.id);
  const next = exists ? items.map((item) => (item.id === conversation.id ? conversation : item)) : [conversation, ...items];
  return [...next].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
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
    api_lookup: "接口",
    flow_trace: "调用链",
    config_lookup: "配置",
    tech_stack: "技术栈",
    symbol_lookup: "符号",
    unknown: "未知",
    call_chain: "调用链",
    api_usage: "接口",
    configuration: "配置",
  };
  return labels[intent];
}

function askResultText(result: AskModeResult) {
  const sections = [
    `生成方式：${result.used_llm ? `百炼模型 ${result.llm_model ?? ""}`.trim() : "规则降级"}`,
    result.fallback_reason ? `降级原因：${result.fallback_reason}` : "",
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
