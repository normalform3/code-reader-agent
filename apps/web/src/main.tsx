import React, { FormEvent, useMemo, useState } from "react";
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
  detected_stack: StackTag[];
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

type Interpretation = {
  project_name: string;
  question: string;
  skill: string;
  prompt_version?: string;
  overview?: string;
  setup_summary?: string;
  final_answer?: string;
  used_llm?: boolean;
  fallback_used?: boolean;
  reading_path?: ReadingPathItem[];
  evidence: Array<{
    path: string;
    reason: string;
    source: string;
    start_line: number | null;
    end_line: number | null;
    excerpt: string | null;
  }>;
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

type Status = "empty" | "loading" | "ready" | "error";

function App() {
  const [projectPath, setProjectPath] = useState("");
  const [question, setQuestion] = useState("这个项目是干什么的？我应该怎么运行，并从哪些文件开始看？");
  const [repoMap, setRepoMap] = useState<RepoMap | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("empty");
  const [error, setError] = useState<string | null>(null);

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

  const importantFiles = useMemo(() => {
    return [...(repoMap?.files ?? [])]
      .sort((left, right) => right.importance_score - left.importance_score || left.path.localeCompare(right.path))
      .slice(0, 10);
  }, [repoMap]);

  async function handleScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectPath.trim()) {
      setError("请先输入本地项目路径。");
      setStatus("error");
      return;
    }

    setStatus("loading");
    setError(null);
    setInterpretation(null);

    try {
      const [repoMapResult, interpretationResult] = await Promise.all([
        postJson<RepoMap>("/api/projects/repo-map", { project_path: projectPath.trim() }),
        postJson<Interpretation>("/api/agent/run", {
          project_path: projectPath.trim(),
          question,
        }),
      ]);
      setRepoMap(repoMapResult);
      setInterpretation(interpretationResult);
      setSelectedModuleId(repoMapResult.modules[0]?.id ?? null);
      setStatus("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "扫描失败，请检查本地 API 是否已启动。");
      setStatus("error");
    }
  }

  async function handleAsk() {
    if (!projectPath.trim()) {
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const result = await postJson<Interpretation>("/api/agent/run", {
        project_path: projectPath.trim(),
        question,
      });
      setInterpretation(result);
      setStatus("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提问失败，请检查本地 API 是否已启动。");
      setStatus("error");
    }
  }

  const statusLabel: Record<Status, string> = {
    empty: "未扫描",
    loading: "扫描中",
    ready: "已完成",
    error: "出错",
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">CR</div>
          <div>
            <h1>CodeReader</h1>
            <p>本地代码库理解 Agent</p>
          </div>
        </div>

        <form className="scan-form" onSubmit={handleScan}>
          <label htmlFor="project-path">项目路径</label>
          <input
            id="project-path"
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder="/Users/nate/project"
          />
          <button type="submit" disabled={status === "loading"}>
            {status === "loading" ? "正在扫描..." : "扫描项目"}
          </button>
        </form>

        <SectionTitle title="技术栈" />
        <div className="tag-list">
          {repoMap?.detected_stack.map((tag) => (
            <span className="tag" key={`${tag.name}-${tag.source}`}>
              {tag.name}
            </span>
          )) ?? <span className="muted">尚未扫描</span>}
        </div>

        <SectionTitle title="入口文件" />
        <div className="path-list">
          {repoMap?.entrypoints.slice(0, 8).map((entrypoint) => (
            <button className="path-row" key={`${entrypoint.kind}-${entrypoint.path}`}>
              <span>{entrypoint.kind}</span>
              <strong>{entrypoint.path}</strong>
            </button>
          )) ?? <span className="muted">等待生成 Repo Map</span>}
        </div>

        <SectionTitle title="文件树" />
        <div className="tree-list">
          {repoMap?.file_tree.slice(0, 36).map((entry) => (
            <div className="tree-row" key={entry.path} style={{ paddingLeft: `${entry.depth * 12 + 8}px` }}>
              <span>{entry.kind === "directory" ? "dir" : "file"}</span>
              <code>{entry.path}</code>
            </div>
          )) ?? <span className="muted">等待扫描文件树</span>}
        </div>

        <SectionTitle title="重要文件" />
        <div className="path-list">
          {importantFiles.length > 0 ? (
            importantFiles.map((file) => (
              <button className="path-row compact" key={file.path}>
                <span>{file.role}</span>
                <strong>{file.path}</strong>
              </button>
            ))
          ) : (
            <span className="muted">等待 Repo Map 评分</span>
          )}
        </div>
      </aside>

      <section className="map-panel">
        <header className="workspace-header">
          <div>
            <p className="kicker">Repo Map</p>
            <h2>{repoMap?.project_name ?? "选择一个 Vue 或 Java 项目"}</h2>
            <span>{repoMap?.project_path ?? "扫描本地代码仓库后，将在这里生成模块地图。"}</span>
          </div>
          <div className="status-pill" data-status={status}>
            {statusLabel[status]}
          </div>
        </header>

        {error ? <div className="error-box">{error}</div> : null}

        <div className="module-grid">
          {repoMap?.modules.map((module) => (
            <button
              className={module.id === selectedModule?.id ? "module-card active" : "module-card"}
              key={module.id}
              onClick={() => setSelectedModuleId(module.id)}
            >
              <span>{module.type}</span>
              <strong>{module.name}</strong>
              <small>{module.key_files.length} 个文件</small>
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

      <aside className="agent-panel">
        <SectionTitle title="Agent 面板" />
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button onClick={handleAsk} disabled={!projectPath.trim() || status === "loading"}>
          基于证据提问
        </button>

        <div className="answer-card">
          <p className="kicker">
            {interpretation?.used_llm ? "LLM Agent" : "Deterministic"} · {interpretation?.skill ?? "project_overview_skill"}
          </p>
          <h3>项目概览</h3>
          <p>{interpretation?.final_answer ?? interpretation?.overview ?? "扫描完成后，Agent 的回答会显示在这里。"}</p>
          {interpretation?.fallback_used ? <span className="warning-note">LLM Agent 已降级为确定性解释。</span> : null}
        </div>

        <div className="answer-card">
          <h3>运行方式</h3>
          <p>{interpretation?.setup_summary ?? "LLM Agent 会在需要时读取配置文件，并基于证据给出运行方式。"}</p>
        </div>

        <div className="answer-card">
          <h3>Agent Steps</h3>
          <div className="step-list">
            {interpretation?.agent_steps?.map((step) => (
              <div className="step-row" data-status={step.status} key={`${step.index}-${step.title}`}>
                <span>{step.kind}</span>
                <strong>{step.title}</strong>
                <small>{step.summary}</small>
              </div>
            )) ?? <span className="muted">LLM Agent 执行后会显示推理步骤</span>}
          </div>
        </div>

        <div className="answer-card">
          <h3>阅读路径</h3>
          <ol>
            {interpretation?.reading_path?.map((item) => (
              <li key={`${item.order}-${item.path}`}>
                <code>{item.path}</code>
                <span>{item.reason}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="answer-card">
          <h3>依据文件</h3>
          <div className="mini-list">
            {interpretation?.read_files.map((path) => <code key={path}>{path}</code>) ?? <span className="muted">暂无读取记录</span>}
          </div>
        </div>

        <div className="answer-card">
          <h3>推荐追问</h3>
          <div className="suggestion-list">
            {interpretation?.suggested_questions.map((suggestion) => (
              <button
                className="suggestion-button"
                key={suggestion}
                onClick={() => {
                  setQuestion(suggestion);
                }}
              >
                {suggestion}
              </button>
            )) ?? <span className="muted">扫描后会生成下一步问题</span>}
          </div>
        </div>
      </aside>

      <section className="evidence-panel">
        <EvidenceColumn
          title="工具调用"
          rows={
            interpretation?.tool_calls.map((call) => `${call.tool_name} · ${call.status} · ${call.output_summary}`) ?? [
              repoMap ? "build_repo_map · success · 模块地图已生成" : "等待工具调用",
            ]
          }
        />
        <EvidenceColumn
          title="证据"
          rows={[
            ...(repoMap?.evidence.map((item) => `${item.path} - ${item.reason}`) ?? []),
            ...(interpretation?.evidence.map((item) => `${item.path} - ${item.reason}`) ?? []),
          ]}
        />
        <EvidenceColumn title="提醒" rows={[...(repoMap?.warnings ?? []), ...(interpretation?.warnings ?? [])]} />
      </section>
    </main>
  );
}

function SectionTitle({ title }: { title: string }) {
  return <h2 className="section-title">{title}</h2>;
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

function EvidenceColumn({ title, rows }: { title: string; rows: string[] }) {
  return (
    <div className="evidence-column">
      <h2>{title}</h2>
      {rows.length > 0 ? rows.map((row) => <p key={row}>{row}</p>) : <p className="muted">暂无记录</p>}
    </div>
  );
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `请求失败，状态码：${response.status}`);
  }
  return response.json() as Promise<T>;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
