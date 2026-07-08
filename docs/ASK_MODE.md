# Ask Mode

Ask 模式发生在首次项目理解报告之后。它不重新全量读取代码库，也不直接把用户问题裸交给模型回答，而是围绕三层上下文构造小而准确的 `ContextPack`，再让百炼 LLM 基于证据组织最终回答。

## 三层上下文

- `Project Memory`：项目定位、技术栈、入口、启动方式、配置、依赖、模块和目录摘要。
- `Code Knowledge Index`：Module Summary、File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index 和 Mapper Relation 候选。
- `Session Memory`：当前话题、关注模块、关注文件/API/流程、上一轮问题和回答摘要。
- `Skill Hints`：由 active skills 贡献的检索关键词、只读工具建议和回答组织提示。

## 节点流程

```text
QueryRewriter
-> IntentClassifier
-> SkillRouter
-> ContextRetriever
-> ToolPlanner
-> ToolExecutor
-> ToolResultProcessor
-> ToolTraceStore
-> ContextBuilder
-> AnswerComposer (Bailian LLM with deterministic fallback)
-> MemoryUpdater
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
- Ask 工具必须注册到运行时 Tool Registry，并通过 Tool Executor 执行。Ask 模式只允许 safe read 工具，不写文件、不运行任意 shell、不执行 Git 操作、不联网抓取代码。
- 工具结果不会全量塞进回答上下文，而是经过 Tool Result Processor 裁剪成 `CodeEvidence` 后进入 `ContextPack`。
- Skill prompt 只能影响回答组织方式，不能作为事实依据。
- Answer Composer 会优先使用模型设置中的百炼模型生成自然语言回答；如果缺少 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL`、模型调用失败或返回空内容，则降级为确定性模板回答，并在 `warnings` 和 trace 中标记。

## 模型设置

- 当前只支持百炼平台的 OpenAI-compatible 接口。
- 模型名称保存在本地 state 的 `model_settings.model`，默认是 `glm-5.1`。
- API Key 和 Base URL 不写入本地 state，也不写入仓库；运行时只读取环境变量 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。
- 前端左侧栏底部的“模型设置”可以查看 `litellm` / `langgraph` 是否安装、环境变量是否配置，并发起一次最小连通性测试。
- 如果本机没有安装 `langgraph`，Ask runtime 使用同顺序 fallback graph；这不影响真实 LLM 调用，只影响工作流框架实现方式。

## Skill 参与方式

Ask 模式不会让 Skill 直接回答用户问题。`SkillRouter` 会先从项目级 `active_skills` 中选择本轮相关 Skill，依据包括问题意图、关键词、Code Knowledge Index 命中和 Session Memory 关注点。只有 routed skills 会参与本轮 Ask。

Skill 只做三件事：

- `query_hints`：为 Context Retriever 增加技术栈相关关键词，例如 `Login.vue`、`auth.ts`、`AuthController`、`SecurityConfig`、`UserMapper`。
- `tool plan hints`：为 Tool Planner 增加只读工具建议，例如 `parse_controller()`、`parse_api_calls()`、`search_keyword("AuthController")`。
- `answer prompts`：告诉 Answer Composer 按技术栈惯例组织说明，例如 Spring Boot 优先讲启动类、配置、接口路径、Controller 方法和相关 Service。

最终回答仍必须来自 Project Memory、Code Knowledge Index 和 Tool Executor 读取到的真实代码证据。

## 输出契约

`/api/agent/ask` 返回：

- `resolved_query`
- `intent_result`
- `tool_plan`
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
- `fallback_used`
- `llm_model`

回答必须尽量包含相关文件路径、候选实现链路和证据说明；如果当前代码中没有明确证据，必须保守说明。

## SSE 流式进度

`/api/agent/ask/stream` 使用同一个 `AskModeRequest` 请求体，返回 `text/event-stream`。它不替代 `/api/agent/ask` 的最终结构化结果，而是在长等待期间把公开进度推给前端。

事件类型：

- `trace`：一个公开 `TraceEvent`，表示 Query Rewriter、Intent Classifier、Skill Router、Context Retriever、Tool Planner、Evidence Collector、Context Builder、Answer Composer 或 Memory Updater 节点完成。
- `tool_plan`：本轮只读工具计划，包括是否需要工具、计划原因和候选工具调用。
- `tool_result`：一个只读工具执行摘要，包括工具名、输入摘要、输出摘要、状态和 reason。
- `answer`：Answer Composer 完成后的回答文本；第一版是节点级流式，不承诺 token 级增量。
- `final`：完整 `AskModeResult`，前端应以该 payload 更新 session memory、trace、warnings 和最终回答。
- `error`：流式执行失败时的错误摘要。

SSE 只展示可给用户看的执行摘要和工具调用理由，不输出模型隐藏推理链。
