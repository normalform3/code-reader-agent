# Ask Mode

Ask 模式发生在首次项目理解报告之后。它不重新全量读取代码库，也不直接把用户问题交给模型回答，而是围绕三层上下文构造小而准确的 `ContextPack`。

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
-> EvidenceCollector
-> ContextBuilder
-> AnswerComposer
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
- 只读工具包括 `read_file`、`search_keyword`、`search_api_path`、`search_symbol`、`parse_dependencies`、`parse_routes`、`parse_api_calls`、`parse_controller` 和 `parse_mapper`。
- 工具结果不会全量塞进回答上下文，而是裁剪成 `CodeEvidence` 后进入 `ContextPack`。
- Skill prompt 只能影响回答组织方式，不能作为事实依据。

## Skill 参与方式

Ask 模式不会让 Skill 直接回答用户问题。`SkillRouter` 会先从项目级 `active_skills` 中选择本轮相关 Skill，依据包括问题意图、关键词、Code Knowledge Index 命中和 Session Memory 关注点。只有 routed skills 会参与本轮 Ask。

Skill 只做三件事：

- `query_hints`：为 Context Retriever 增加技术栈相关关键词，例如 `Login.vue`、`auth.ts`、`AuthController`、`SecurityConfig`、`UserMapper`。
- `tool plan hints`：为 Tool Planner 增加只读工具建议，例如 `parse_controller()`、`parse_api_calls()`、`search_keyword("AuthController")`。
- `answer prompts`：告诉 Answer Composer 按技术栈惯例组织说明，例如 Spring Boot 优先讲启动类、配置、接口路径、Controller 方法和相关 Service。

最终回答仍必须来自 Project Memory、Code Knowledge Index 和 Evidence Collector 读取到的真实代码证据。

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

回答必须尽量包含相关文件路径、候选实现链路和证据说明；如果当前代码中没有明确证据，必须保守说明。
