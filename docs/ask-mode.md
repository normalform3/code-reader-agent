# Ask Mode

Ask 模式发生在首次项目理解报告之后。它不会重新全量读取代码库，也不会让模型直接凭空回答，而是围绕 Project Memory、Code Knowledge Index、Session Memory 和 routed skills 构造小而准确的 Context Pack，再让百炼 LLM 基于证据组织最终回答。

## 流程

```text
用户问题
-> Query Rewriter
-> Intent Classifier
-> SkillRouter
-> Context Retriever
-> Tool Planner
-> Tool Executor
-> Tool Result Processor
-> Tool Trace Store
-> Context Builder
-> Answer Composer (Bailian LLM with deterministic fallback)
-> Memory Updater
```

## SkillRouter

问题级 SkillRouter 只从项目扫描阶段得到的 active skills 中选择本轮相关 Skill。选择依据包括：

- 问题意图。
- 关键词和 resolved query。
- Code Knowledge Index 命中的文件、API、symbol、route、flow、mapper。
- Session Memory 中的关注文件、API 和流程。

被选中的 routed skills 会提供：

- query hints：帮助 Context Retriever 检索索引。
- tool plan hints：帮助 Tool Planner 规划只读工具。
- answer prompts：帮助 Answer Composer 按技术栈惯例组织回答。

## 只读证据规则

Skill prompt 不能作为事实依据。只要问题涉及具体实现、具体文件、接口、方法、字段、权限判断或数据来源，Ask 模式必须通过只读工具读取或搜索真实代码。

可用只读工具包括：

- `read_file`
- `read_file_chunk`
- `get_file_metadata`
- `search_keyword`
- `search_file_by_name`
- `search_api_path`
- `search_symbol`
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

所有 Ask 工具必须先注册到运行时 Tool Registry，再由 Tool Executor 执行。Ask 模式只允许 `permission=read`、`risk_level=safe` 且声明支持 `ask` mode 的工具；不会写文件、删除文件、运行任意 shell、执行 Git 操作或联网抓取代码。

工具原始结果必须先经过 Tool Result Processor，裁剪成 `CodeEvidence` 后才能进入 Context Pack。回答需要尽量包含文件路径、候选调用链和代码依据；没有明确证据时必须保守说明。

Answer Composer 会优先使用模型设置中的百炼模型生成自然语言回答；如果缺少 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL`、模型调用失败或返回空内容，则降级为确定性模板回答，并在 `warnings` 和 trace 中标记。

## 模型设置

当前只支持百炼平台的 OpenAI-compatible 接口。模型名称保存在本地 state 的 `model_settings.model`，默认是 `glm-5.1`；API Key 和 Base URL 不写入本地 state，也不写入仓库，只从运行环境读取 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。

前端左侧栏底部的“模型设置”可以查看 `litellm` / `langgraph` 是否安装、环境变量是否配置，并发起一次最小连通性测试。如果本机没有安装 `langgraph`，Ask runtime 使用同顺序 fallback graph；这不影响真实 LLM 调用，只影响工作流框架实现方式。

## 为什么不是复杂多 Agent 路由

当前 MVP 的重点是陌生代码库理解，而不是通用自动编排。轻量 SkillRouter 已经能降低上下文噪声和无效工具调用，同时保持 trace 可解释。后续可以扩展工具级路由和复杂 Skill 编排，但要继续遵守只读工具和 evidence 边界。
