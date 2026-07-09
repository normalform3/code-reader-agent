# CodeReader Agent 项目计划

## 项目愿景

CodeReader Agent 希望成为一个面向陌生 Java Web / 前后端项目的代码库理解 Agent。用户输入公开 GitHub 项目链接后，它能先创建分析任务、制定 plan、调用只读工具、组织上下文、选择技术栈 skill，并生成结构化项目解读报告；报告生成后，系统进入 Ask 模式，围绕 Project Memory 和只读工具持续回答追问。

它的核心目标不是自动替用户改代码，也不是普通 Ask 问答，而是把陌生代码库整理成可导航、可追踪、可复用的知识结构。

## 核心用户痛点

- 陌生项目缺少清晰入口。
- 启动命令、框架依赖、路由、状态管理、请求封装、登录认证和后端分层结构分散在不同文件。
- 普通代码问答缺少可视化结构和证据追踪。
- 大模型容易根据文件名或经验猜测，难以证明结论来自真实代码。
- 开发者需要一个能快速生成 onboarding 路径的本地工具。

## 产品定位

CodeReader Agent 是目标驱动的本地可视化代码库理解 Agent：

- 本地运行，公开 GitHub 仓库链接是 MVP 主入口。
- 本地项目路径仅作为内部扫描契约和开发调试能力保留。
- 使用 Repo Map 作为结构化项目地图。
- 使用 Planner、Tool Executor、Context Manager、Skill Registry、Analyzer、Report Writer 和 Trace Logger 组织分析过程。
- 使用 evidence 机制约束报告结论。
- 使用 Web UI 展示模块、文件、分析计划、上下文快照、工具调用、报告、证据和 Ask 追问。
- 使用 Project Memory 保存项目定位、技术栈、入口、启动方式、配置、依赖、模块、目录摘要。
- 使用 Code Knowledge Index 保存 Module Summary、File Summary、API Index、Symbol Index 和 Flow Index。
- 使用 Session Memory 支持跨轮追问、指代消解和当前关注点延续。
- 第一阶段优先支持 Vue/Vite 与 Java/Spring Boot 项目，先跑通前后端项目理解报告闭环。

## Phase 0：项目规划与文档准备

功能清单：

- 建立项目目录结构。
- 创建核心设计文档。
- 创建初始 Python 包结构。
- 创建 `pyproject.toml`。
- 明确 MVP、非目标、架构、UI、Repo Map、tools、skills、context manager 和多 Agent 协作。

验收标准：

- 文档覆盖项目定位、架构和 MVP 边界。
- 仓库中存在后续实现所需的基础目录。
- 不要求提供完整可运行产品；当前仓库已有扫描 API 和确定性项目解读 API 的早期实现，后续计划以此为基础继续收敛。

## Phase 1：本地 API 服务与项目扫描

功能清单：

- 创建 FastAPI 服务。
- 支持公开 GitHub 仓库导入到本地只读缓存。
- 提供项目扫描 API。
- 扫描文件树。
- 读取 `package.json`。
- 识别包管理器、依赖、启动命令、构建命令。
- 识别 Vue / Vite / TypeScript / Pinia / Vue Router / Axios。
- 识别 Java / Maven / Gradle / Spring Boot。
- 识别基础目录结构、入口文件和配置文件。

验收标准：

- 用户能输入公开 GitHub 仓库链接，或使用本地项目路径。
- API 能返回技术栈和文件树摘要。
- Vue 项目能识别前端入口、路由、状态管理和请求封装候选位置。
- Java 项目能识别应用入口、包结构、Controller、Service、Repository 和配置文件候选位置。
- 扫描过程有基础工具调用记录。

## Phase 2：Repo Map Schema 与 Builder

功能清单：

- 实现 Repo Map Pydantic models。
- 根据扫描结果生成基础模块树。
- 识别入口文件、重要文件、配置文件。
- 保存 Repo Map 到本地结构化存储。

验收标准：

- 给定 Vue/Vite 项目能生成基础 Repo Map。
- 给定 Java/Spring Boot 项目能生成基础 Repo Map。
- Repo Map 包含模块、文件、入口、依赖和证据。
- 回答时可以基于 Repo Map 选择上下文。

## Phase 3：本地 Web UI 原型

功能清单：

- 创建 Vite + React + TypeScript 前端。
- 实现项目选择入口。
- 展示扫描进度。
- 展示技术栈、文件树、模块树和项目概览。
- 展示工具调用记录和已读取文件。

验收标准：

- 用户可以在浏览器完成一次项目扫描。
- UI 能清楚展示 Repo Map 的主要字段。

## Phase 4：项目总览解释与阅读路线

功能清单：

- 支持项目总览 skill。
- 支持启动方式分析 skill。
- 支持推荐阅读路径。
- 支持生成确定性项目总览和阅读建议。
- 设计版本化单 Agent prompt。
- 在未接入真实 LLM 前提供确定性 fallback 解读。

验收标准：

- 能回答“这个项目是干什么的？”
- 能回答“这个项目怎么运行？”
- 能回答“我应该从哪些文件开始看？”
- 回答中展示依据文件路径。
- API 返回 prompt version、prompt messages、evidence 和 warnings。
- 不把未读取源码内容伪装成证据。

## Phase 4.5：可信理解闭环

功能清单：

- 将 evidence 从路径级扩展为可选片段级，包含行号、摘录、收集工具和收集时间。
- 实现安全只读工具 `read_file` 和 `search_code`，默认拒绝敏感文件并防止路径穿越。
- 增加 legacy Skill Router，支持项目总览、运行方式和前端结构三个确定性 skill；MVP 主入口后续使用 Skill Registry。
- Web UI 展示文件树、重要文件、模块证据片段、已读取文件、工具调用、warnings 和推荐追问。
- 对登录/API 类问题只展示候选证据和不确定提示，不声称完成完整调用链。

验收标准：

- Vue 和 Java 示例项目仍能完成扫描、Repo Map 和确定性解释。
- API 返回兼容旧字段，并新增工具调用、已读取文件和片段 evidence。
- UI 能让用户看到 Agent 读取了哪些文件、依据了哪些片段、哪些结论不确定。
- `python -m pytest`、`python -m compileall src apps` 和前端 build 通过。

## Phase 5：目标驱动项目理解报告

Phase 5 先稳定 `/api/agent/run` 作为 MVP 分析任务入口，再把报告沉淀为 Project Memory。

## Phase 5.0：Planner / Context / Report / Trace 契约

功能清单：

- `/api/agent/run` 返回 `task_id`、`analysis_goal`、`analysis_plan`、`selected_skills`、`context_snapshot`、`report` 和 `trace_events`。
- deterministic Planner 根据用户目标生成固定分析计划。
- Skill Registry 根据 Repo Map 技术栈选择 `CodebaseOverviewSkill`、`VueSkill`、`SpringBootSkill` 等 skill。
- Context Manager 输出项目上下文、任务上下文、符号上下文和当前记忆上下文快照。
- Report Writer 输出项目地图、模块说明、关键入口、阅读路线、调用链候选、证据和不确定点。
- Trace Logger 记录计划、工具调用、上下文更新、Agent 步骤和报告生成。
- 返回 `project_memory`，并保存到本地 JSON state。

验收标准：

- LLM 不可用时，deterministic fallback 也能返回完整 plan、context、report 和 trace。
- UI 能展示 Planner 计划、Skill Registry、Context Snapshot、Report 和 Trace Logger。
- 不新增写文件、运行项目命令或 Git 操作能力。

## Phase 5.1：最小 LLM Agent Loop

功能清单：

- 接入百炼平台 `glm-5.1`，通过 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL` 配置。
- 使用现有 `litellm` 依赖，不新增生产依赖。
- 让 LLM 根据自然语言问题选择只读工具。
- 支持 `scan_project`、`build_repo_map`、`read_file`、`search_code` 四个工具。
- 记录每一轮 LLM 决策、工具调用、工具结果和最终回答。
- LLM 不可用、输出不合法或超步数时降级到确定性解释。

验收标准：

- `/api/agent/run` 能返回 `AgentRunResult`。
- UI 能展示 LLM Agent / Deterministic 模式、agent steps、降级提醒和降级原因。
- 自动化测试使用 mock LLM，不依赖真实网络。
- 只读安全边界不被 LLM 绕过。

## Phase 5.2：Ask 模式

功能清单：

- 新增 `/api/agent/ask`。
- 支持项目总览、模块解释、文件解释、接口定位、流程追踪、配置查找、技术栈、符号定位和 unknown 意图分类。
- 优先检索 Project Memory、Module Summary、File Summary、API Index、Symbol Index、Flow Index 和 Session Memory。
- 使用 LangGraph `StateGraph` 表达 `QueryRewriter -> IntentClassifier -> ContextRetriever -> ToolPlanner -> EvidenceCollector -> ContextBuilder -> AnswerComposer -> MemoryUpdater`。
- 当记忆不足时调用只读工具补证据。
- 构造 `ContextPack`，只放入回答所需的项目上下文、会话上下文、索引命中项和代码证据。
- 回答包含直接回答、相关文件、候选实现路径、关键代码说明和参考依据。
- 更新 Session Memory，支持连续追问。

验收标准：

- Ask 回答能区分项目记忆、真实代码证据和不确定推测。
- 工具调用记录包含工具名、输入、输出、状态和调用原因。
- API 返回指代消解、意图结果、工具计划、Context Pack 和代码证据，前端 Ask Trace 可展示。
- 不新增写文件、运行项目命令或 Git 操作能力。

## Phase 6：专项 Skills 与 Reviewer

功能清单：

- 登录认证流程分析。
- API 请求链路分析。
- 页面数据来源分析。
- 状态管理分析。
- Java 分层结构分析。
- Reviewer 检查证据完整性和过度猜测。
- Agent State 和 Tool Call 可视化。

验收标准：

- UI 能展示当前 skill、Agent 步骤、工具调用和证据。
- Reviewer 能标记缺少证据的结论。

## Phase 7：Codebase Map 可视化增强

功能清单：

- 模块关系图。
- 调用链图。
- 页面到 API 的数据流图。
- 登录认证流程图。

验收标准：

- 关键流程能以图形方式展示。
- 图中节点可以追溯到文件和证据。

## Phase 8：自动修改和 PR 生成（后续）

功能清单：

- 自动修改代码。
- PR 生成。
- 变更导航。

验收标准：

- 必须在只读项目理解和 Ask 模式稳定后再设计。
- 任何写操作都需要明确工具边界、用户确认和安全审计。

## 最终简历展示效果

项目最终应展示为一个真实可用的 Codebase Understanding Agent：开发者输入陌生 Java Web / 前后端项目链接后，系统能自动创建分析任务、生成 Repo Map、组织上下文、选择 skill、输出结构化报告，并通过 evidence 和 trace 证明每个结论来自真实代码。
