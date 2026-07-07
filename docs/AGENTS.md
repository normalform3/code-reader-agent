# 多 Agent 协作设计

## 设计目标

多 Agent 协作不是为了增加复杂度，而是为了让代码理解任务有清晰分工、可展示过程和可验证结果。MVP 先在单进程内模拟 Planner、Tool Executor、Context Manager、Skill Registry、Analyzer、Report Writer 和 Trace Logger，不实现真正并发 Agent。

公开 GitHub 仓库链接是 MVP 主入口；本地项目路径只保留为内部扫描契约和开发调试能力。

## Planner Agent

职责：

- 理解用户问题。
- 判断任务类型和分析目标。
- 生成分析计划。
- 设定完成条件。

可用 tools：

- 不直接读取大量文件。
- 可以读取 Repo Map 摘要。

输出：

- analysis_goal
- analysis_plan
- expected_output

## Tool Executor

职责：

- 执行只读工具。
- 统一记录工具输入、输出、错误和证据。
- 拒绝写文件、运行项目命令、Git 操作和敏感文件读取。

允许工具：

- `scan_project`
- `build_repo_map`
- `read_file`
- `search_code`

输出：

- tool_calls
- evidence
- read_files
- warnings

## Context Manager

职责：

- 组织项目上下文、任务上下文、符号上下文和当前记忆上下文。
- 不把整个代码库一次性塞给模型。
- 输出可展示的 `ContextSnapshot`。

输出：

- project_context
- task_context
- symbol_context
- memory_context
- evidence_count
- read_files

## Skill Registry

职责：

- 根据 Repo Map 和 detected stack 选择技术栈 skill。
- MVP 支持 `CodebaseOverviewSkill`、`VueSkill`、`SpringBootSkill`。
- API/auth 等专项 skill 在 MVP 中只输出候选证据，不声称完整链路追踪。

输出：

- selected_skills

## Explorer Agent

职责：

- 根据 skill 搜索代码。
- 读取关键文件。
- 收集 evidence。
- 记录工具调用。

当前状态：

- MVP 中由 Tool Executor + 只读工具承担 Explorer 的最小职责。

输出：

- candidate_files
- evidence
- warnings
- missing_information

## Analyzer Agent

职责：

- 分析代码结构。
- 识别模块关系。
- 分析调用链和数据流候选。
- 将证据组织成解释结构。

可用 tools：

- `build_repo_map`
- 后续 `trace_imports`
- 后续 `trace_api_flow`

输出：

- findings
- relationships
- confidence
- uncertainty

## Report Writer

职责：

- 生成面向用户的结构化项目解读报告。
- 输出项目地图、模块说明、关键入口、阅读路线、调用链候选和不确定点。
- 保留证据引用。

输出：

- report
- cited_files
- uncertainties

## Trace Logger

职责：

- 记录 Planner 计划。
- 记录 Skill Registry 选择结果。
- 记录 Context Snapshot 更新。
- 记录工具调用和 Agent 步骤。
- 记录 Report Writer 最终产物。

输出：

- trace_events

## Reviewer Agent

职责：

- 检查回答是否有依据。
- 检查是否遗漏关键文件。
- 检查是否过度猜测。
- 标记不确定点。

当前状态：

- Reviewer 属于后续增强；MVP 先通过 warnings、evidence 和 trace 暴露不确定点。

输出：

- review_status
- unsupported_claims
- missing_evidence
- revised_warnings

## Agent 间数据结构

```text
agent_task:
- task_id
- analysis_goal
- user_question
- selected_skills
- repo_map_id
- analysis_plan
- context_snapshot
- tool_calls
- evidence
- findings
- report
- trace_events
- review
- status
```

## 示例流程：登录流程分析

用户问：“登录流程是怎么实现的？”

Planner Agent：

- 识别为 `auth_flow_skill`。

Explorer Agent：

- 搜索 `login`、`token`、`auth`、`beforeEach`、`interceptor`、`Authorization` 等关键词。
- 读取登录页面、用户 store、API 文件、request 封装和 router 文件。

Analyzer Agent：

- 分析登录提交、token 保存、路由守卫和请求拦截逻辑。

Writer Agent：

- 生成登录流程说明、调用链、关键文件列表和不确定点。

Reviewer Agent：

- 检查回答是否引用证据文件。
- 标记没有读取到的链路缺口。

UI：

- 展示 Planner 计划、当前 skill、上下文快照、已读取文件、工具调用记录、报告依据和警告。

## UI 展示要求

每次任务需要展示：

- Planner 计划。
- Skill Registry 选择结果。
- Context Snapshot。
- 结构化项目解读报告。
- Trace Logger 执行轨迹。
- 当前 Agent 步骤。
- 工具调用记录。
- 已读取文件。
- evidence。
- warnings / Reviewer 警告。

## Ask 模式 Agent 编排

报告生成后，右侧 Ask 边栏不再重新执行完整报告流程，而是进入基于项目记忆的追问流程。

当前实现位于 `code_reader_agent.runtime.ask_mode`，使用 LangGraph `StateGraph` 表达节点；当本地依赖暂时不可用时，runtime 使用同顺序 fallback 方便离线测试。

节点职责：

- `IntentClassifier`：把用户问题识别为项目总览、模块解释、文件解释、调用链、接口、配置或技术栈。
- `ContextRetriever`：优先检索 Project Memory、Module Summary、File Summary、API Index、Flow Index 和 Session Memory。
- `ToolPlanner`：判断记忆是否足够；不足时规划只读工具调用。
- `EvidenceCollector`：执行 `read_file`、`search_keyword`、`search_symbol`、`parse_dependencies`、`parse_routes`、`parse_api_calls`、`parse_controller`、`parse_mapper` 等只读工具。
- `AnswerComposer`：输出直接回答、相关文件、候选实现路径、关键代码说明和参考依据。
- `MemoryUpdater`：保存最近问题、意图、引用文件、引用 API 和回答摘要，支持跨轮追问。

Ask 模式边界：

- 不修改被分析代码。
- 不运行项目命令。
- 不执行 Git 操作。
- 不读取敏感文件。
- 调用链和 API Index 当前仍为候选级，不声称精准全量 AST 追踪。

## Phase 4：单 Agent 项目解读

Phase 4 先不实现完整多 Agent 编排，而是提供一个可验证的单 Agent 解读闭环。

职责：

- 接收用户问题和扫描结果。
- 固定选择 `project_overview_skill`。
- 基于 package 信息、技术栈标签、入口文件和 warnings 构造上下文。
- 生成版本化 prompt messages，供后续 LLM provider 使用。
- 在没有 LLM 的情况下返回确定性 onboarding 草稿。

输入：

- `project_path`
- `question`
- `ProjectScanResult`

输出：

- `skill`
- `prompt_version`
- `prompt_messages`
- `overview`
- `setup_summary`
- `reading_path`
- `evidence`
- `warnings`

边界：

- 不额外读取源码全文。
- 不调用外部 LLM。
- 不执行项目命令。
- 不伪造 Repo Map 或 evidence。
- 缺少 README、package scripts 或入口文件时必须返回 warning。

## Phase 4.5：最小 Skill Router + 可信 Evidence

Phase 4.5 仍不实现完整多 Agent 编排，但单 Agent 解读不再固定使用 `project_overview_skill`。

职责：

- 根据用户问题确定性选择 `project_overview_skill`、`setup_analysis_skill` 或 `frontend_analysis_skill`。
- 通过只读工具读取配置、入口和前端结构候选文件。
- 对登录/API 类问题只搜索候选关键词，不生成完整链路结论。
- 返回工具调用、已读取文件、片段 evidence、warnings 和推荐追问。

输出新增：

- `tool_calls`
- `read_files`
- `suggested_questions`
- evidence 的 `start_line`、`end_line`、`excerpt`

边界：

- 不调用外部 LLM。
- 不执行被分析项目命令。
- 不读取 `.env`、私钥、证书等敏感文件。
- 不把候选搜索结果说成完整认证或 API 调用链。

## Phase 5.0：目标驱动 Agent 任务契约

Phase 5.0 将 `/api/agent/run` 作为 MVP 主入口。它不要求完整多 Agent 并发，但必须返回可展示的分析任务结构。

输出：

- `task_id`
- `analysis_goal`
- `analysis_plan`
- `selected_skills`
- `context_snapshot`
- `project_manual`
- `report`
- `trace_events`
- 兼容旧字段：`final_answer`、`evidence`、`tool_calls`、`read_files`、`agent_steps`、`fallback_result`

`project_manual` 是首次自动生成的项目说明书，固定包含项目总览、技术栈说明、模块作用、项目入口、真实目录树、关键目录解释、evidence 和 uncertainties。报告生成后，系统会从 `project_manual` 和 Repo Map 派生 `project_memory`；后续追问通过 `/api/agent/ask` 检索 Project Memory 和 Session Memory，不再把每轮追问都当作完整报告重新生成。

边界：

- LLM 不可用时仍返回完整结构。
- Tool Executor 仍只允许只读工具。
- 不开放写文件、运行项目命令或 Git 操作。

## Phase 5.1：Minimal LLM Agent Loop

Phase 5.1 接入真实 LLM 决策层，但仍保持单 Agent、只读、安全边界。

职责：

- 用户自然语言问题进入 LLM。
- LLM 根据工具定义选择只读工具。
- 后端执行工具并把结果回填给 LLM。
- LLM 可以继续调用工具，或输出最终结构化 JSON 回答。
- 如果 LLM 不可用、超步数或输出不合法，系统降级到 deterministic fallback，但仍返回 Phase 5.0 的完整分析任务结构。

允许工具：

- `scan_project`
- `build_repo_map`
- `read_file`
- `search_code`

禁止能力：

- 写文件。
- 运行 shell 或被分析项目命令。
- Git 操作。
- 读取 `.env`、私钥、证书等敏感文件。
- 声称未通过工具读取的内容是 evidence。

默认模型配置：

- 模型：`glm-5.1`
- Provider：百炼平台 OpenAI-compatible 接口。
- 环境变量：`DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`。
