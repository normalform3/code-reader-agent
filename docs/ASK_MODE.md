# Ask Mode

Ask 模式发生在首次项目理解报告之后。它不重新全量读取代码库，也不直接把用户问题裸交给模型回答，而是围绕三层上下文构造小而准确的 `ContextPack`，再让百炼 LLM 基于证据组织最终回答。

## 三层上下文

- `Project Memory`：项目定位、技术栈、入口、启动方式、配置、依赖、模块和目录摘要。
- `Code Knowledge Index`：Module Summary、File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index 和 Mapper Relation 候选。
- `Session Memory`：当前话题、关注模块、关注文件/API/流程、最近 8 轮问答、历史摘要和已归档轮次数。
- `Skill Hints`：由 active skills 贡献的检索关键词、只读工具建议和回答组织提示。

同一个项目可以拥有多个 Ask Conversation。每个 conversation 独立保存消息和 `Session Memory`，但共享项目说明书、`Project Memory` 和轻量索引认知。

## 持久化边界

- 持久化：项目说明书、`Project Memory`、索引摘要、Ask conversation 消息和 `Session Memory` 关注点。
- 不持久化：`ContextPack`、工具原始输出、搜索结果全文、`CodeEvidence.code_snippet` 和本轮读取到的代码片段。
- 具体实现类问题必须在每轮 Ask 中重新通过只读工具读取当前工作区代码。Project Memory、Session Memory 和索引只用于候选定位与指代消解，当前工作区读取结果才是最终事实来源。
- 如果候选文件或接口来自历史认知但当前工作区无法读到对应代码，Ask 必须返回 warning，说明项目认知可能过期或当前代码未找到明确证据。

## 节点流程

```text
QueryRewriter
-> LLMIntentClassifier
-> SkillRouter
-> ContextRetriever
-> GoalPlanner (仅 flow_trace)
-> LLMToolPlanner <-> EvidenceCollector
-> EvidenceReviewer (仅 flow_trace，可回到 Tool Planner 重规划)
-> ContextBuilder
-> AnswerComposer (普通 Ask) / InvestigationReporter (flow_trace)
-> MemoryUpdater
-> SessionSummarizer
```

## 意图类型

- `project_overview`
- `module_explanation`
- `file_explanation`
- `api_lookup`
- `flow_trace`
- `config_lookup`
- `tech_stack`
- `symbol_lookup`
- `unknown`

旧 state 中的 `api_usage`、`call_chain` 和 `configuration` 会在运行时兼容为新的 intent 名称。

## 只读证据规则

- 项目总览、技术栈、模块概览优先使用结构化记忆。
- 只要问题涉及具体实现、具体文件、接口、方法、字段、权限判断或数据来源，就必须通过只读工具读取或搜索真实代码。
- 只读工具包括 `read_file`、`read_file_chunk`、`get_file_metadata`、`search_keyword`、`search_file_by_name`、`search_api_path`、`search_symbol`、`parse_dependencies`、`parse_package_scripts`、`parse_routes`、`parse_api_calls`、`parse_controller`、`parse_mapper` 和 `query_*_index`。
- Ask 工具必须注册到运行时 Tool Registry，并通过 Tool Executor 执行。`LLMToolPlanner` 只接收 Registry 中的 safe/read Ask 工具 schema，并由模型按需选择；工具执行仍受参数、权限、路径边界和 timeout 校验。
- 工具结果不会全量塞进回答上下文，而是经过 Tool Result Processor 裁剪成 `CodeEvidence` 后进入 `ContextPack`。
- Skill prompt 只能影响回答组织方式，不能作为事实依据。
- LLM 完成意图识别、工具决策和最终回答。工具循环最多 3 轮、8 次调用；工具结果只以裁剪后的 evidence/summary 回传给模型。关键 LLM 阶段未配置、失败或输出非法时，同步 Ask 返回 HTTP 503，且不写入会话；不会降级为规则型 Ask 回答。

## 模型设置

- 当前只支持百炼平台的 OpenAI-compatible 接口。
- 模型名称保存在本地 state 的 `model_settings.model`，默认是 `glm-5.1`。
- API Key 和 Base URL 不写入本地 state，也不写入仓库；运行时只读取环境变量 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。
- 前端左侧栏底部的“模型设置”可以查看 `litellm` / `langgraph` 是否安装、环境变量是否配置，并发起一次最小连通性测试。
- Ask 必须使用已安装的 LangGraph 编译图执行；缺少 `langgraph` 视为服务不可用并返回 HTTP 503。

## Skill 参与方式

Ask 模式不会让 Skill 直接回答用户问题。`SkillRouter` 会先从项目级 `active_skills` 中选择本轮相关 Skill，依据包括问题意图、关键词、Code Knowledge Index 命中和 Session Memory 关注点。只有 routed skills 会参与本轮 Ask。

Skill 只做三件事：

- `query_hints`：为 Context Retriever 增加技术栈相关关键词，例如 `Login.vue`、`auth.ts`、`AuthController`、`SecurityConfig`、`UserMapper`。
- `tool plan hints`：为 LLMToolPlanner 提供技术栈级关键词和候选工具方向，例如 `parse_controller()`、`parse_api_calls()`、`search_keyword("AuthController")`；模型仍自行决定是否调用。
- `answer prompts`：告诉 Answer Composer 按技术栈惯例组织说明，例如 Spring Boot 优先讲启动类、配置、接口路径、Controller 方法和相关 Service。

最终回答仍必须来自 Project Memory、Code Knowledge Index 和 Tool Executor 读取到的真实代码证据。

## 输出契约

`/api/agent/ask` 返回：

- `resolved_query`
- `intent_result`
- `tool_plan`
- `investigation`：仅 `flow_trace` 返回，包含目标计划、已确认/未确认流程步骤、结论、证据覆盖审查和停止原因。
- `context_pack`
- `routed_skills`
- `query_hints`
- `code_evidence`
- `answer`
- `related_files`
- `implementation_path`
- `references`
- `tool_calls`
- `trace_events`
- `session_memory`
- `used_llm`
- `llm_model`

回答必须尽量包含相关文件路径、候选实现链路和证据说明；如果当前代码中没有明确证据，必须保守说明。

`AskModeRequest` 可携带 `conversation_id`。携带时，后端从该 Ask conversation 读取 `Session Memory`，本轮结束后只把新的消息和 `Session Memory` 写回该 conversation，不写入 project-level legacy session memory。超过 8 轮时，`SessionSummarizer` 使用旧摘要和超窗轮次生成新的历史摘要；摘要失败时保留旧摘要（没有旧摘要则丢弃超窗轮次）并返回 warning。

## SSE 流式进度

`/api/agent/ask/stream` 使用同一个 `AskModeRequest` 请求体，返回 `text/event-stream`。它不替代 `/api/agent/ask` 的最终结构化结果，而是在长等待期间把公开进度推给前端。

事件类型：

- `trace`：一个公开 `TraceEvent`，表示 Query Rewriter、LLM Intent Classifier、Skill Router、Context Retriever、Goal Planner、LLM Tool Planner、Evidence Collector、Evidence Reviewer、Context Builder、Answer Composer、Investigation Reporter、Memory Updater 或 Session Summarizer 节点完成。
- `goal_plan`：流程调查的可验证证据目标。
- `evidence_review`：流程调查的已满足目标、缺口和停止决定。
- `replan`：Evidence Reviewer 要求 Tool Planner 围绕证据缺口继续调查。
- `tool_plan`：本轮只读工具计划，包括是否需要工具、计划原因和候选工具调用。
- `tool_result`：一个只读工具执行摘要，包括工具名、输入摘要、输出摘要、状态和 reason。
- `answer`：Answer Composer 或 Investigation Reporter 完成后的回答文本；第一版是节点级流式，不承诺 token 级增量。
- `final`：完整 `AskModeResult`，前端应以该 payload 更新 session memory、trace、warnings 和最终回答；如果请求携带 `conversation_id`，事件还会带回更新后的 Ask conversation 摘要。
- `error`：流式执行失败时的错误摘要。

当 LLM 在任何关键阶段不可用或失败时，SSE 会在已发出的公开进度后返回 `error`，不会发送 `final` 或写入会话。

SSE 只展示可给用户看的执行摘要和工具调用理由，不输出模型隐藏推理链。
