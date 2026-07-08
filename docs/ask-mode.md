# Ask Mode

Ask 模式发生在首次项目理解报告之后。它不会重新全量读取代码库，也不会让模型直接凭空回答，而是围绕 Project Memory、Code Knowledge Index、Session Memory 和 routed skills 构造小而准确的 Context Pack。

## 流程

```text
用户问题
-> Query Rewriter
-> Intent Classifier
-> SkillRouter
-> Context Retriever
-> Tool Planner
-> Evidence Collector
-> Context Builder
-> Answer Composer
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
- `search_keyword`
- `search_api_path`
- `search_symbol`
- `parse_dependencies`
- `parse_routes`
- `parse_api_calls`
- `parse_controller`
- `parse_mapper`

回答需要尽量包含文件路径、候选调用链和代码依据；没有明确证据时必须保守说明。

## 为什么不是复杂多 Agent 路由

当前 MVP 的重点是陌生代码库理解，而不是通用自动编排。轻量 SkillRouter 已经能降低上下文噪声和无效工具调用，同时保持 trace 可解释。后续可以扩展工具级路由和复杂 Skill 编排，但要继续遵守只读工具和 evidence 边界。
