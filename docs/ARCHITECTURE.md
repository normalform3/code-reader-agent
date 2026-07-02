# 架构设计

## 总体架构

推荐数据流：

```text
Frontend UI
-> Local API Server
-> Agent Runtime
-> Planner Agent
-> Skill Router
-> Explorer Agent
-> Tool Executor
-> Context Manager
-> Repo Map Builder
-> Analyzer Agent
-> Writer Agent
-> Reviewer Agent
-> UI 展示结果
```

用户流程：

```text
用户选择项目目录
-> 后端扫描文件树
-> 工具系统读取配置和关键文件
-> Repo Map Builder 生成结构化项目地图
-> Context Manager 根据用户问题选择相关上下文
-> Agent 分析并生成解释
-> 前端展示模块图、文件树、回答、证据和工具调用过程
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

- 项目路径输入和扫描触发。
- 展示扫描进度。
- 展示 Project Explorer、Codebase Map、Agent Panel、Evidence Panel。
- 展示 Repo Map、工具调用、已读取文件和回答证据。
- 通过 SSE 或 WebSocket 接收任务事件。

## Local API Server 层

技术选择：

- FastAPI
- Pydantic

职责：

- 提供本地 HTTP API。
- 管理扫描任务和 Agent 任务。
- 校验用户输入的项目路径。
- 调用 Agent Runtime。
- 向前端返回 Repo Map、任务状态和事件流。

Phase 1 计划 API：

- `POST /api/projects/scan`
- `POST /api/projects/import-github`
- `POST /api/projects/repo-map`
- `POST /api/agent/project-interpretation`
- `POST /api/agent/questions`
- `GET /api/tasks/{task_id}/events`

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

Phase 4 最小实现：

- `POST /api/agent/project-interpretation` 基于项目路径触发一次扫描和单 Agent 解读。
- 路由层仍只负责请求映射，解读逻辑位于 `code_reader_agent.interpreter.interpret_project`。
- 解读结果包含 `prompt_version`、`prompt_messages`、overview、setup summary、reading path、evidence 和 warnings。
- 当前不接真实 LLM provider；`prompt_messages` 是后续接入模型的稳定边界，API 同时返回确定性 fallback 解读。

## Agent Runtime 层

职责：

- 保存 Agent State。
- 调度 Planner、Explorer、Analyzer、Writer、Reviewer。
- 记录工具调用过程。
- 管理任务生命周期。
- 将中间状态发送给 UI。

Phase 0 只保留目录和设计，不实现完整 runtime。

Phase 4 最小单 Agent runtime：

- 使用 `project_overview_skill` 作为固定 skill。
- 输入为 `ProjectScanResult`，不额外读取源码全文。
- 生成版本化 prompt：`project_interpreter_v1`。
- 输出确定性 onboarding 草稿，保证没有 LLM 时也能验证 API 行为。
- 后续接入 LLM 时，应复用同一 prompt contract，并保留 deterministic fallback。

## Tool System 层

职责：

- 封装只读工具。
- 统一记录工具输入、输出、耗时、错误和证据。
- 限制工具访问范围。
- 对写文件、运行命令等高风险行为要求用户确认。

第一版工具默认只读。

## Skill System 层

职责：

- 根据用户问题选择分析 skill。
- 为不同任务定义搜索关键词、优先读取文件、上下文选择策略和输出格式。
- 避免每个问题都从零设计分析流程。

## Context Manager 层

职责：

- 不把整个代码库一次性塞给模型。
- 根据 Repo Map、用户问题和 skill 选择相关文件。
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
- 保存任务事件和工具调用记录。
- 后续可用 SQLite 存储。

Phase 0 不实现存储。

## Observability / Logs 层

职责：

- 记录扫描进度。
- 记录工具调用。
- 记录 Agent 步骤。
- 记录警告、不确定结论和失败原因。

这些信息需要在 Evidence Panel 中展示，方便用户判断回答是否可信。
