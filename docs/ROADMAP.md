# Roadmap

## Phase 0：项目规划与文档准备

- 创建项目目录结构。
- 创建核心文档。
- 创建 Python 包占位。
- 明确 MVP 边界。
- 记录关键技术决策。

## Phase 1：本地 API 服务 + 项目扫描 + Vue/Java 技术栈识别

- 创建 FastAPI 应用。
- 实现项目路径校验。
- 实现文件树扫描。
- 读取 `package.json`。
- 读取 `pom.xml`、`build.gradle`、`settings.gradle`。
- 识别包管理器、scripts 和依赖。
- 识别 Vue3、Vite、TypeScript、Pinia、Vue Router、Axios。
- 识别 Java、Maven、Gradle、Spring Boot、Spring Web、Spring Security、MyBatis/JPA、JUnit。
- 识别 Vue 应用入口、路由、store、请求封装候选位置。
- 识别 Java 应用入口、Controller、Service、Repository、配置文件候选位置。

## Phase 2：Repo Map Schema + Repo Map Builder

- 实现 Pydantic models。
- 生成基础 Repo Map。
- 识别入口文件和重要文件。
- 识别核心模块、接口调用链候选、登录认证候选和状态管理候选。
- 输出 warnings 和 evidence。

## Phase 3：本地 Web UI 原型

- 创建 Vite + React + TypeScript 前端。
- 实现项目输入。
- 展示扫描进度。
- 展示技术栈、文件树、模块树和项目概览。

## Phase 4：项目总览解释 + 阅读路线生成

- 实现 project overview skill。
- 实现 setup analysis skill。
- 实现推荐阅读路径。
- 生成确定性项目总览和阅读建议。
- 设计 `project_interpreter_v1` 单 Agent prompt。
- 暴露项目解读 API，返回 prompt payload、证据和确定性 fallback 结果。

## 当前实现状态

截至当前版本，Phase 1-6.0 已形成“项目理解 + Ask 模式”MVP 雏形：

- `POST /api/projects/scan` 支持 Vue/Java 基础扫描。
- `POST /api/projects/repo-map` 支持基础 Repo Map 生成。
- `apps/web` 提供 Vite + React + TypeScript 本地工作台原型。
- `POST /api/agent/project-interpretation` 支持确定性项目总览、启动建议和推荐阅读路径。
- Repo Map 和 Agent 解释支持片段级 evidence、已读取文件和工具调用记录。
- `POST /api/agent/run` 支持最小只读 LLM tool loop 和 deterministic fallback。
- Agent run 已返回 `task_id`、`analysis_goal`、`analysis_plan`、`selected_skills`、`context_snapshot`、`report` 和 `trace_events`。
- Agent run 已返回并保存 `project_memory`。
- `POST /api/agent/ask` 支持报告后的 Ask 模式，返回 intent、answer、related files、implementation path、references、tool calls、trace events 和 session memory。
- Ask 模式支持项目总览、模块解释、文件解释、调用链、接口、配置和技术栈 7 类意图。
- Skill Registry 可根据 Repo Map 技术栈选择 `CodebaseOverviewSkill`、`VueSkill` 和 `SpringBootSkill`。

仍未完成：

- 精准 AST 级调用链。
- 任务事件流和持久化任务历史。
- 持久化扫描历史。
- 真实 LLM provider 接入。
- 完整多 Agent 并发编排和 Reviewer。
- 自动修改代码、PR 生成和变更导航。

## Phase 4.5：可信理解闭环

- 补齐片段级 evidence：文件路径、行号、摘录、收集工具和收集时间。
- 实现安全只读工具：`read_file` 和 `search_code`。
- 默认拒绝读取 `.env`、私钥、证书等敏感文件，并限制路径不能越过项目根目录。
- Web UI 展示文件树、重要文件、模块证据片段、已读取文件、工具调用和 warnings。
- Legacy Skill Router 支持 `project_overview_skill`、`setup_analysis_skill`、`frontend_analysis_skill`；MVP 主入口使用 Skill Registry 输出 `CodebaseOverviewSkill`、`VueSkill`、`SpringBootSkill`。
- 登录/API 问题仅识别候选文件和关键词，不声称完成调用链追踪。
- 保持 Vue / Java 为 MVP 技术栈，不在该阶段扩展 React、Next.js、FastAPI 等新栈。

## Phase 5.0：目标驱动 Agent 任务契约

- `/api/agent/run` 作为 MVP 分析任务入口。
- Planner 输出 `analysis_plan`。
- Skill Registry 输出 `selected_skills`。
- Context Manager 输出 `context_snapshot`。
- Report Writer 输出 `report`，包含项目地图、模块说明、关键入口、阅读路线、调用链候选、证据和不确定点。
- Trace Logger 输出 `trace_events`。
- LLM 不可用时 deterministic fallback 仍返回完整任务结构。

## Phase 5.1：最小 LLM Agent Loop

- 接入百炼平台 `glm-5.1`。
- 使用 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL` 环境变量。
- LLM 根据用户自然语言问题选择只读工具。
- 支持 `scan_project`、`build_repo_map`、`read_file`、`search_code`。
- 记录 agent steps、tool calls、evidence、read files 和 fallback warnings。
- LLM 不可用或输出不合法时降级到确定性解释。

## Phase 5.2：Project Memory 与 Ask 模式

- 从 Repo Map 和 Project Manual 生成 Project Memory。
- 保存 Project Memory、Module Summary、File Summary、API Index 和 Flow Index。
- Ask 模式通过 Intent Classifier、Context Retriever、Tool Planner、Evidence Collector、Answer Composer 和 Memory Updater 回答追问。
- Ask 模式只调用只读工具，不运行项目命令，不修改代码。

## Phase 6：专项 Skills 与 Reviewer

- `SpringBootSkill` 增强。
- `VueSkill` 增强。
- auth flow skill。
- api flow skill。
- page data flow skill。
- state management skill。
- java layered architecture skill。
- Reviewer 检查证据和过度猜测。

## Phase 7：自动修改与变更导航（后续）

- 自动修改代码。
- PR 生成。
- 变更导航。
- 这些能力必须在只读理解闭环稳定后再设计。

## Phase 8：Codebase Map 可视化增强

- 模块关系图。
- 调用链图。
- 页面到 API 的数据流。
- 登录认证流程图。

## Phase 9：TUI / 桌面端体验优化

- 评估 Tauri 或 Electron。
- 优化本地文件选择体验。
- 保持 Web UI 作为核心产品形态。

## Phase 10：更多技术栈和真实项目 demo

- React。
- Next.js。
- FastAPI。
- Express。
- 更复杂的 Java 微服务项目。
- 多语言项目。
- 真实开源项目 demo。
