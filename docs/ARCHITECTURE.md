# 架构设计

## 总体架构

推荐数据流：

```text
Frontend UI
-> Local API Server
-> Local JSON State
-> Agent Runtime
-> Planner Agent
-> Tool Executor
-> Context Manager
-> Skill Registry
-> Repo Map Builder
-> Analyzer Agent
-> Report Writer
-> Trace Logger
-> Reviewer Agent
-> UI 展示结果
```

用户流程：

```text
用户输入公开 GitHub 仓库链接
-> 导入仓库到本地只读缓存
-> 创建分析任务
-> Planner 生成分析计划
-> Tool Executor 调用只读工具扫描、读取、搜索和构建 Repo Map
-> Context Manager 组织项目、任务、符号和当前记忆上下文
-> Skill Registry 根据技术栈检测并激活 skill
-> 只有 ActiveSkill 参与 scan 和 Code Knowledge Index 构建
-> Analyzer 生成理解结果
-> Report Writer 输出结构化项目解读报告
-> Trace Logger 记录计划、工具调用、上下文更新和最终产物
-> 报告沉淀为 Project Memory
-> 前端展示 Repo Map、报告、trace、证据和工具调用过程
-> 用户在右侧 Ask 边栏追问
-> Query Rewriter 结合 Session Memory 做指代消解
-> Intent Classifier 识别问题类型
-> SkillRouter 从 active skills 中选择本轮相关 Skill
-> Context Retriever 检索 Project Memory / Module Summary / File Summary / API Index / Symbol Index / Flow Index / Session Memory
-> Tool Planner 判断是否需要只读工具
-> Evidence Collector 读取真实代码、配置或索引
-> Context Builder 构造小而准确的 Context Pack
-> Answer Composer 生成带文件路径和依据的回答
-> Memory Updater 更新 Session Memory
```

第一步支持 Vue 和 Java 项目。Vue 侧优先识别 Vite 应用入口、路由、状态管理、请求封装和页面目录；Java 侧优先识别 Maven/Gradle/Spring Boot 项目入口、包结构、Controller、Service、Repository、配置文件和测试目录。

## Frontend UI 层

技术选择：

- React
- Vite
- TypeScript
- Tailwind CSS
- shadcn/ui
- React Flow

职责：

- 公开 GitHub 仓库链接输入和分析任务触发。
- 展示扫描进度。
- 展示 Project Explorer、Codebase Map、Agent Panel、Evidence Panel。
- 展示 ChatGPT 风格的项目会话侧边栏。
- 通过内置弹窗展示工具管理和 Skill 管理，不切换或重载项目工作台。
- 展示 Repo Map、Planner 计划、Skill Registry、Context Snapshot、Report、Trace Logger、工具调用、已读取文件和回答证据。
- 通过 SSE 或 WebSocket 接收任务事件。

## Local API Server 层

技术选择：

- FastAPI
- Pydantic

职责：

- 提供本地 HTTP API。
- 管理扫描任务和 Agent 任务。
- 校验公开 GitHub 链接和内部项目路径。
- 调用 Agent Runtime。
- 向前端返回 Repo Map、任务状态和事件流。

Phase 1 计划 API：

- `POST /api/projects/scan`
- `POST /api/projects/import-github`
- `POST /api/projects/repo-map`
- `POST /api/agent/project-interpretation`
- `POST /api/agent/run`
- `POST /api/agent/ask`
- `GET /api/tasks/{task_id}/events`

本地会话与 registry API：

- `GET /api/projects/history`
- `POST /api/projects/history`
- `PATCH /api/projects/history/{project_id}`
- `DELETE /api/projects/history/{project_id}`
- `GET /api/registry/tools`
- `POST /api/registry/tools`
- `PATCH /api/registry/tools/{tool_id}`
- `DELETE /api/registry/tools/{tool_id}`
- `GET /api/registry/skills`
- `POST /api/registry/skills`
- `PATCH /api/registry/skills/{skill_id}`
- `DELETE /api/registry/skills/{skill_id}`

Phase 1 最小实现：

- `apps/api/main.py` 提供 `POST /api/projects/scan` 草案。
- 路由层只负责请求校验和错误映射，扫描逻辑位于 `code_reader_agent.scanner.scan_project`。
- 扫描结果使用 Pydantic model 返回，包含文件树摘要、前端 package 信息、`java_build` Java 构建配置摘要、技术栈标签、入口文件和 warnings。
- `POST /api/projects/repo-map` 使用 `code_reader_agent.repo_map.builder.build_repo_map` 返回基础模块、文件角色、入口和 evidence。
- 当前不实现任务队列、持久化和事件流。

GitHub Import 层：

- `POST /api/projects/import-github` 接收公开 GitHub 仓库链接。
- 路由层只负责请求映射和错误映射，导入逻辑位于 `code_reader_agent.github_importer.import_github_repository`。
- 导入层只允许 `https://github.com/owner/repo` 或 `.git` 形式，使用 `git clone --depth 1` 下载到本地 `.codereader/repos` 缓存。
- 导入完成后返回本地缓存 `project_path`，后续 Repo Map 和 Agent 分析继续复用现有项目路径契约。
- 导入层不运行仓库代码、不安装依赖、不执行项目脚本。

Phase 5 MVP 主入口：

- `POST /api/agent/run` 是目标驱动分析任务入口。
- 返回兼容旧字段的同时新增 `task_id`、`analysis_goal`、`analysis_plan`、`selected_skills`、`context_snapshot`、`report` 和 `trace_events`。
- LLM 不可用时使用 deterministic fallback，但仍返回完整 plan、context、report 和 trace。
- 模型层位于 `code_reader_agent.runtime.llm_client`，默认使用百炼 OpenAI-compatible `glm-5.1`，从 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL` 读取配置。
- 当前不实现持久化任务队列或 SSE 事件流。

Ask 模式入口：

- `POST /api/agent/ask` 是报告生成后的右侧追问入口。
- 输入 `project_path`、`question` 和可选 `session_memory`。
- 返回 `resolved_query`、`intent_result`、`tool_plan`、`context_pack`、`code_evidence`、`intent`、`answer`、`related_files`、`implementation_path`、`key_code_notes`、`references`、`tool_calls`、`trace_events` 和 `session_memory`。
- 返回还包含 `used_llm`、`fallback_used` 和 `llm_model`，用于区分真实百炼回答和确定性降级回答。
- 当前支持 8 类意图：项目总览、模块解释、文件解释、接口定位、流程追踪、配置查找、技术栈和符号定位。
- Ask 模式只允许只读工具，不写被分析仓库，不运行项目命令，不执行 Git 操作。

模型设置入口：

- `GET /api/model-settings` 返回当前百炼模型名、`litellm` / `langgraph` 安装状态，以及 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` 是否配置。
- `POST /api/model-settings` 只保存模型名称，不保存 API Key、Base URL 或其他密钥。
- `POST /api/model-settings/test` 发起最小百炼连通性测试，返回脱敏结果。
- 当前只支持百炼平台 OpenAI-compatible 调用。

Legacy Phase 4 单 Agent 解读：

- `POST /api/agent/project-interpretation` 基于项目路径触发一次扫描和单 Agent 解读。
- 路由层仍只负责请求映射，解读逻辑位于 `code_reader_agent.interpreter.interpret_project`。
- 解读结果包含 `prompt_version`、`prompt_messages`、overview、setup summary、reading path、evidence 和 warnings。
- 该 legacy 入口不直接调用模型；`prompt_messages` 是稳定模型输入边界，API 同时返回确定性 fallback 解读。

## Agent Runtime 层

职责：

- 保存 Agent State 的请求内快照。
- 调度 Planner、Tool Executor、Context Manager、Skill Registry、Analyzer、Report Writer 和 Trace Logger。
- 记录工具调用过程。
- 管理任务生命周期。
- 将中间状态发送给 UI。

当前 MVP runtime：

- 使用 `code_reader_agent.runtime.analysis` 生成 deterministic plan、skill selection、context snapshot、report 和 trace。
- LLM loop 只允许模型选择 `scan_project`、`build_repo_map`、`read_file` 和 `search_code`。
- 没有 LLM provider、LLM 输出非法或超过步数时，降级到 deterministic fallback。
- fallback 仍必须返回完整分析任务结构，保证本地 demo 不依赖真实模型。

Ask runtime：

- `code_reader_agent.runtime.ask_mode` 使用 LangGraph `StateGraph` 表达节点流程。
- 节点顺序固定为 `QueryRewriter -> IntentClassifier -> ContextRetriever -> ToolPlanner -> EvidenceCollector -> ContextBuilder -> AnswerComposer -> MemoryUpdater`。
- 如果本地开发环境暂时无法安装 `langgraph`，runtime 会使用同顺序的最小 fallback 以便离线测试；生产依赖仍在 `pyproject.toml` 中声明为 `langgraph`。
- Ask 使用百炼 LLM 基于 `ContextPack` 组织最终回答；LLM 不能绕过只读工具和 evidence 边界。缺少模型配置或调用失败时，Answer Composer 会降级为确定性模板。

## Tool System 层

职责：

- 封装只读工具。
- 通过运行时 Tool Registry 管理工具定义、权限、风险等级、可用模式、参数 schema、timeout 和 handler。
- 通过 Tool Executor 统一执行工具调用，校验 Ask 只读权限、参数和项目路径边界。
- 通过 Tool Result Processor 将原始结果裁剪成 CodeEvidence。
- 通过 Tool Trace Store 记录工具调用原因、耗时、时间戳和结果摘要。
- 统一记录工具输入、输出、耗时、错误和证据。
- 限制工具访问范围。
- 对写文件、运行命令等高风险行为要求用户确认。

第一版 Ask 工具默认只读。Ask 模式只允许 `permission=read`、`risk_level=safe` 且 `available_in_modes` 包含 `ask` 的工具；不写文件、不运行项目命令、不执行 Git 操作。

Ask 模式新增只读工具：

- `list_files`
- `read_file`
- `read_file_chunk`
- `get_file_metadata`
- `search_keyword`
- `search_symbol`
- `search_api_path`
- `search_file_by_name`
- `parse_dependencies`
- `parse_package_scripts`
- `parse_routes`
- `parse_api_calls`
- `parse_controller`
- `parse_mapper`
- `query_project_memory`
- `query_code_index`
- `query_api_index`
- `query_flow_index`
- `query_symbol_index`

每次工具调用记录 `tool_name`、输入参数、输入摘要、输出摘要、状态、错误、`reason`、耗时和时间戳，前端可展示为什么调用该工具。

## Skill Registry 层

职责：

- 注册技术栈 Skill，并根据 Repo Map、依赖、文件结构和轻量解析结果检测 active skills。
- 执行 active skill 的扫描函数，把结果合并进 ProjectMemory 的 Code Knowledge Index。
- 为 Ask 模式提供 query hints、只读 tool plan hints 和回答组织提示。
- 避免每个问题都从零设计分析流程，同时避免让 Skill 直接替代 evidence-based 回答。

Skill 定义不是单纯提示词，而是：

```text
Skill = 技术栈名称 + 激活条件 + 扫描函数 + 解析规则 + 索引构建逻辑 + 检索提示 + 回答提示词
```

当前 MVP runtime skill：

- `CodebaseOverviewSkill`
- `JavaWebSkill`
- `VueSkill`
- `SpringBootSkill`
- `MyBatisSkill`
- `RestApiSkill`

首次分析时，Skill Registry 在 Repo Map 之后运行，返回 active skill 名称、置信度和激活原因；各 Skill 的扫描结果会沉淀到 File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index 和 Mapper Relation 候选。

Ask 模式中，SkillRouter 只从 active skills 中选择本轮相关 Skill。路由依据包括问题意图、关键词、Code Knowledge Index 命中和 Session Memory 关注点。只有 routed skills 会参与上下文获取和工具规划：它可以建议 `search_keyword("AuthController")`、`parse_controller()` 或 `parse_api_calls()`，但最终回答仍必须来自 Project Memory、Code Knowledge Index 和只读工具 evidence。

## Context Manager 层

职责：

- 不把整个代码库一次性塞给模型。
- 根据 Repo Map、用户问题和 skill 选择相关文件。
- 输出 `ContextSnapshot`，包含 project context、task context、symbol context、memory context、evidence count 和 read files。
- 对长文件、命令输出和历史消息做摘要压缩。
- 保留 evidence context，支持 UI 展示和 Reviewer 检查。

## Repo Map Builder 层

职责：

- 汇总扫描结果。
- 识别技术栈、入口、模块、文件角色、依赖和证据。
- 生成前端可展示、Agent 可检索的结构化 Repo Map。
- 将确定性信息和模型推断分开记录。

Phase 1 最小扫描结果不是完整 Repo Map，只提供后续 Builder 需要的确定性输入：

- 项目路径和项目名。
- 过滤后的文件树摘要。
- `package.json` 中的 scripts 和依赖。
- `pom.xml`、`build.gradle`、`settings.gradle` 中的构建工具和依赖摘要。
- 技术栈标签和基础入口文件。
- Vue 项目的路由、store、请求封装候选位置。
- Java 项目的 Controller、Service、Repository、配置文件候选位置。
- 可展示给 UI 和 Reviewer 的 warnings。

## Memory / Storage 层

职责：

- 保存 Repo Map。
- 保存扫描历史。
- 保存左侧项目会话历史。
- 保存 tools 和 skills 的本地 registry 元数据。
- 保存任务事件和工具调用记录。
- 后续可用 SQLite 存储。

当前本地状态使用 JSON 文件，不新增生产依赖：

- 默认 `.codereader/state.json`
- 可通过 `CODEREADER_STATE_DIR/state.json` 覆盖

当前保存内容：

- `project_sessions`：左侧历史项目会话，只保存项目元数据和内部 `project_path`，删除历史不会删除缓存仓库。
- `tools`：内置和自定义工具元数据，包含 `details` 结构化详情；内置项不能真正删除，删除会变成禁用。
- `skills`：内置和自定义 skill 元数据，包含 `details` 结构化详情；自定义 skill 第一版只用于管理弹窗展示，不参与 Agent 路由。
- `project_memories`：按稳定 `project_path` hash 保存 Project Memory 和 Code Knowledge Index，包含 Project Memory、Module Summary、File Summary、API Index、Symbol Index 和 Flow Index。
- `session_memories`：按项目保存短期 Ask 会话记忆，包含当前话题、关注模块、关注文件/API/流程、上一轮问题和回答摘要，用于跨轮追问。
- `model_settings`：保存当前百炼模型名。密钥和私有 endpoint 不进入 state，只从本机运行环境读取。

读取旧 JSON 状态时，如果内置 tool/skill 缺少 `details`，Local State 会自动补齐默认详情，并保留用户已编辑的名称、说明、补充说明和启用状态。

本地 JSON 损坏时，API 返回明确错误，不静默重置，以免误丢用户配置。

## Observability / Logs 层

职责：

- 记录扫描进度。
- 记录工具调用。
- 记录 Agent 步骤。
- 记录 Planner 计划、Skill Registry 结果、Context Snapshot 更新和 Report Writer 输出。
- 记录警告、不确定结论和失败原因。

这些信息需要在 Evidence Panel 中展示，方便用户判断回答是否可信。
