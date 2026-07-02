# Context Manager

## 设计目标

Context Manager 负责为 Agent 选择必要上下文。它不能把整个代码库一次性塞给模型，而是先构建索引，再按任务选择关键文件和证据。

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

### Answer Context

包含：

- 最终回答需要引用的 evidence。
- 回答结构。
- 不确定点。
- 后续建议问题。

## 上下文选择策略

1. Planner 判断用户问题类型。
2. Skill Router 选择 skill。
3. Context Manager 根据 skill 从 Repo Map 选择候选模块和文件。
4. Explorer 使用工具补充读取缺失证据。
5. Analyzer 使用 Evidence Context 分析。
6. Writer 生成回答。
7. Reviewer 检查回答是否超出 evidence。

## 压缩策略

- 长文件只读取相关片段。
- 命令输出需要摘要。
- 文件树需要按目录摘要。
- 历史消息只保留当前任务相关内容。
- Repo Map 保留结构化字段，避免反复传入大段自然语言。

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
