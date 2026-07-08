# Skill System

Skill 是 CodeReader Agent 的技术栈级代码理解插件。它不是 prompt 模板，也不是让模型绕过证据直接回答的捷径。

## Skill 包含什么

每个 Skill 需要提供：

- `name`：Skill 名称。
- `detect(repo_map)`：项目级激活判断，返回 matched、confidence 和 reason。
- `scan(repo_map)`：只读扫描和轻量解析结果。
- Code Knowledge Index 写入逻辑：file summaries、API index、symbol index、flow index、route index 等。
- `get_query_hints()`：Ask 检索提示。
- `plan_tools()`：Ask 只读工具建议，只生成 `PlannedToolCall`，不直接执行工具。
- `get_answer_prompt()`：回答组织提示。

## Skill 与 Code Knowledge Index

Skill 扫描结果会写入 `ProjectMemory` 的 Code Knowledge Index，而不是只生成自然语言说明。

当前主要索引包括：

- Module Summary。
- File Summary。
- API Index。
- Symbol Index。
- Flow Index。
- Route Index。
- Frontend API Call Index。
- Data Model Index。
- Mapper Relation 候选。

Ask 模式优先检索这些结构化索引。索引不足或问题涉及具体实现时，仍然通过运行时 Tool Registry 和 Tool Executor 调用只读工具读取真实代码。

## 项目级 Skill 路由

项目扫描阶段使用 `SkillRegistry.route_project_skills(repo_map)`：

```text
Repo Map
-> detect all built-in skills
-> ActiveSkill(name, confidence, reason)
-> run scan only for ActiveSkill
-> merge scan results into Code Knowledge Index
```

这保证未命中的技术栈 Skill 不参与扫描和索引构建。

## 问题级 Skill 路由

Ask 阶段使用 `SkillRegistry.route_query_skills(...)`。它只从 `ProjectMemory.active_skills` 中选择本轮相关 Skill。

路由信号包括：

- Intent Classifier 的问题意图。
- resolved query 和关键词。
- 命中的文件、API、symbol。
- Code Knowledge Index 中的 API、route、frontend call、mapper、data model 等条目。
- Session Memory 的关注模块、文件、API 和流程。

被选中的 routed skills 才会贡献 query hints、tool plan hints 和 answer prompts。Skill 不直接调用 `read_file`、`search_keyword` 等底层函数，也不能把 prompt 当作事实依据。

## 当前支持的 Skill

- `JavaWebSkill`
- `SpringBootSkill`
- `MyBatisSkill`
- `VueSkill`
- `RestApiSkill`

## 后续扩展

后续可以增加工具级路由，例如根据 routed skill 和 intent 精确选择 `parse_controller`、`parse_mapper` 或 `parse_routes` 的执行顺序；也可以做更复杂的 Skill 编排。但当前阶段保持轻量，避免为了展示架构而引入多 Agent 噪声。
