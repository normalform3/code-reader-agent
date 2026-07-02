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

## Phase 4：项目总览问答 + onboarding 总结生成

- 实现 project overview skill。
- 实现 setup analysis skill。
- 实现推荐阅读路径。
- 生成 onboarding 总结。
- 设计 `project_interpreter_v1` 单 Agent prompt。
- 暴露项目解读 API，返回 prompt payload、证据和确定性 fallback 结果。

## 当前实现状态

截至当前版本，Phase 1-4 已形成最小闭环：

- `POST /api/projects/scan` 支持 Vue/Java 基础扫描。
- `POST /api/projects/repo-map` 支持基础 Repo Map 生成。
- `apps/web` 提供 Vite + React + TypeScript 本地工作台原型。
- `POST /api/agent/project-interpretation` 支持确定性项目总览、启动建议和推荐阅读路径。
- Repo Map 和 Agent 解释支持片段级 evidence、已读取文件和工具调用记录。
- Agent 解释已具备最小 Skill Router，可路由到项目总览、运行方式和前端结构分析。

仍未完成：

- 精准 AST 级调用链。
- 任务事件流和持久化任务历史。
- 持久化扫描历史。
- 真实 LLM provider 接入。
- 多 Agent 编排和 Reviewer。

## Phase 4.5：可信理解闭环

- 补齐片段级 evidence：文件路径、行号、摘录、收集工具和收集时间。
- 实现安全只读工具：`read_file` 和 `search_code`。
- 默认拒绝读取 `.env`、私钥、证书等敏感文件，并限制路径不能越过项目根目录。
- Web UI 展示文件树、重要文件、模块证据片段、已读取文件、工具调用和 warnings。
- Skill Router 支持 `project_overview_skill`、`setup_analysis_skill`、`frontend_analysis_skill`。
- 登录/API 问题仅识别候选文件和关键词，不声称完成调用链追踪。
- 保持 Vue / Java 为 MVP 技术栈，不在该阶段扩展 React、Next.js、FastAPI 等新栈。

## Phase 5：Skills 机制增强

- auth flow skill。
- api flow skill。
- page data flow skill。
- state management skill。
- java layered architecture skill。

## Phase 6：多 Agent 协作 + Reviewer + 证据追踪

- Planner、Explorer、Analyzer、Writer、Reviewer 编排。
- 展示 Agent 步骤。
- Reviewer 检查证据和过度猜测。

## Phase 7：Codebase Map 可视化增强

- 模块关系图。
- 调用链图。
- 页面到 API 的数据流。
- 登录认证流程图。

## Phase 8：TUI / 桌面端体验优化

- 评估 Tauri 或 Electron。
- 优化本地文件选择体验。
- 保持 Web UI 作为核心产品形态。

## Phase 9：更多技术栈和真实项目 demo

- React。
- Next.js。
- FastAPI。
- Express。
- 更复杂的 Java 微服务项目。
- 多语言项目。
- 真实开源项目 demo。
