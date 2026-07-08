# Context Manager

## 设计目标

Context Manager 负责为代码库理解 Agent 选择和组织必要上下文。它不能把整个代码库一次性塞给模型，而是先依赖 Repo Map 和只读工具结果，再按分析任务选择关键文件、符号和证据。

MVP 中 Context Manager 有两条路径：

- `/api/agent/run` 返回 `context_snapshot`，用于展示首次项目理解报告使用了哪些项目上下文、任务上下文、符号上下文和当前记忆上下文。
- `/api/agent/ask` 先做指代消解，再检索结构化 `ProjectMemory`、Code Knowledge Index 和 `SessionMemory`，按需调用只读工具补充代码证据，最后构造 `ContextPack` 回答。

Ask 模式的上下文分三层：

- `Project Memory`：项目定位、技术栈、启动方式、入口、配置、依赖、模块和目录摘要。
- `Code Knowledge Index`：Module Summary、File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index 和 Mapper Relation 候选。
- `Session Memory`：当前话题、关注模块、关注文件/API/流程、上一轮问题和回答摘要。
- `Routed Skill Hints`：问题级 SkillRouter 选择出的本轮相关 Skill 提供 query hints、tool plan hints 和 answer prompts。

## 上下文类型

### Global Context

包含：

- 系统规则。
- 工具说明。
- 安全规则。
- 回答约束。

### Project Context

包含：

- 技术栈。
- 目录结构。
- 配置文件。
- 入口文件。
- 包管理器和 scripts。

### Repo Map Context

包含：

- 文件角色。
- 模块划分。
- 关键符号。
- 模块关系。
- 重要 evidence。

### Task Context

包含：

- 当前用户问题。
- 当前分析目标。
- 当前 skill。
- 已完成工具调用。

### Evidence Context

包含：

- 真正读取过的文件片段。
- 路径。
- 行号。
- 工具调用来源。
- 采集原因。

### History Context

包含：

- 历史追问。
- 历史分析结果。
- 用户选择过的模块或文件。

Ask 模式已经保存短期会话记忆：

- 最近问题。
- 指代消解后的问题。
- 问题意图。
- 当前话题和关注模块。
- 引用过的文件。
- 引用过的 API。
- 引用过的流程。
- 回答摘要。

这让“那这个接口在哪里调用？”这类追问可以沿用上一轮上下文。

### Project Memory

首次项目理解报告会沉淀结构化项目记忆：

- `project_memory`：项目定位、技术栈、启动方式、模块列表。
- `module_summaries`：模块名称、职责、入口文件、Controller / Service / View / API 文件。
- `file_summaries`：关键文件路径、文件职责、文件角色和符号候选。
- `api_index`：接口路径、HTTP 方法、后端方法、后端文件和前端调用位置。
- `symbol_index`：类、方法、函数、组件、接口或类型所在文件。
- `flow_index`：调用链或登录/auth/API 流程候选。
- `route_index`：Vue/前端路由候选。
- `frontend_api_call_index`：前端 axios/fetch/request 调用候选。
- `data_model_index`：实体、Mapper、SQL 和 table 候选。
- `mapper_relations`：Mapper 到实体或 table 的候选关系。

### Answer Context

包含：

- 最终回答需要引用的 evidence。
- 回答结构。
- 不确定点。
- 后续建议问题。

## 上下文选择策略

1. Planner 将用户目标转成分析计划。
2. Tool Executor 调用只读工具生成扫描结果、Repo Map、文件片段和搜索结果。
3. Skill Registry 根据 Repo Map 激活技术栈 Skill，并把扫描结果写入 Code Knowledge Index。
4. Context Manager 根据目标、active skills 和索引组织 project context、task context、symbol context、memory context。
5. Analyzer 使用 Evidence Context 分析。
6. Report Writer 生成结构化项目解读报告。
7. Trace Logger 记录上下文更新和最终产物。
8. 后续 Reviewer 检查报告是否超出 evidence。

Ask 模式选择策略：

1. Query Rewriter 结合 Session Memory 处理“这个 / 那个 / 继续”等追问。
2. Intent Classifier 识别项目总览、模块解释、文件解释、接口定位、流程追踪、配置查找、技术栈、符号定位和 unknown。
3. SkillRouter 从 active skills 中选择本轮 routed skills。
4. Context Retriever 优先从 Project Memory、Module Summary、File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index、Mapper Relation 和 Session Memory 检索，并使用 routed skill query hints。
5. Tool Planner 判断上下文是否足够，并合并 routed skill tool plan hints；凡涉及具体实现、具体文件、具体接口、具体方法或字段的问题都规划只读工具。
6. Evidence Collector 调用 `read_file`、`search_keyword`、`search_api_path`、`parse_dependencies`、`parse_api_calls`、`parse_controller` 等只读工具，并裁剪为短证据。
7. Context Builder 构造 `ContextPack`，只放入回答所需项目上下文、会话上下文、索引命中项、routed skill answer prompts 和代码证据。
8. Answer Composer 输出直接回答、相关文件、候选实现路径、关键说明和参考依据。
9. Memory Updater 写回 Session Memory。

## Context Snapshot 输出

```text
context_snapshot:
- project_context
- task_context
- symbol_context
- memory_context
- evidence_count
- read_files
```

该结构是前端展示用的压缩快照，不替代完整 Repo Map。

## 压缩策略

- 长文件只读取相关片段。
- 命令输出需要摘要。
- 文件树需要按目录摘要。
- 历史消息只保留当前任务相关内容。
- Repo Map 保留结构化字段，避免反复传入大段自然语言。
- `ContextPack` 使用字符数近似控制预算，优先级为用户明确提到的文件、会话关注文件、API/Flow 命中文件、模块相关文件和项目摘要。

## 证据策略

- 回答必须尽量基于已读取文件。
- 关键结论需要引用路径。
- 不确定的地方必须说明不确定。
- UI 需要展示 Agent 使用过的上下文和证据。
- Reviewer 需要标记缺少 evidence 的结论。

## Repo Map 复用

Repo Map 应保存为结构化文件或数据库记录，方便：

- 后续追问复用。
- 前端快速展示。
- Context Manager 快速筛选文件。
- 对比重新扫描结果。

当前实现中，`ProjectMemory` 从 Repo Map、Project Manual 和 Skill 扫描结果派生，并存放在 `.codereader/state.json`。Ask 回答优先使用该结构化记忆；当记忆不足时，再调用只读工具读取真实代码。`knowledge_index_version` 用于标记 Skill 增强索引版本，旧 state 会在 Ask 模式中自动重建。
