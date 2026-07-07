# MVP 范围

## MVP 目标

第一版目标是跑通一个最小但完整的目标驱动代码库理解闭环：

用户输入一个公开 GitHub 仓库链接后，CodeReader Agent 创建分析任务，由 Planner 生成分析计划，Tool Executor 调用只读工具，Context Manager 组织上下文，Skill Registry 选择技术栈 skill，Analyzer 生成理解结果，Report Writer 输出结构化项目解读报告，Trace Logger 记录全过程。本地项目路径只作为内部扫描契约和开发调试能力保留。

当前 MVP 支持范围：

- Vue：优先覆盖 Vue3 / Vite / TypeScript 项目，识别路由、状态管理、请求封装和页面目录。
- Java：优先覆盖 Maven / Gradle / Spring Boot 项目，识别应用入口、包结构、Controller、Service、Repository、配置文件和测试目录。

当前实现已跑通 MVP 雏形：公开 GitHub 导入、本地扫描、基础 Repo Map、React/Vite 工作台、确定性项目解读、最小只读 LLM tool loop、结构化报告字段和基础测试。下一步重点不是扩展语言或开放写代码能力，而是稳定 plan、context、report、trace 和 evidence 的展示质量。

## MVP 用户流程

1. 用户打开本地 Web UI。
2. 用户输入一个公开 GitHub 仓库链接。
3. 系统导入仓库到本地只读缓存并创建分析任务。
4. Planner 生成分析计划。
5. Tool Executor 调用 `scan_project`、`build_repo_map`、`read_file`、`search_code` 等只读工具。
6. Context Manager 组织项目上下文、任务上下文、符号上下文和当前记忆上下文。
7. Skill Registry 根据技术栈选择 `CodebaseOverviewSkill`、`VueSkill`、`SpringBootSkill` 等 skill。
8. Analyzer 基于 Repo Map、工具结果和 evidence 生成理解结果。
9. Report Writer 输出项目地图、模块说明、关键入口、阅读路线、调用链候选和不确定点。
10. Trace Logger 记录计划、工具调用、上下文更新和最终产物。
11. UI 展示 Repo Map、结构化报告、trace、工具调用和 evidence。

## MVP 功能列表

- GitHub 仓库链接输入。
- 本地项目路径作为内部扫描契约保留。
- 文件树扫描。
- `package.json` 读取。
- Java 构建配置读取。
- 技术栈识别。
- 包管理器识别。
- Java 构建工具识别。
- 启动命令和构建命令识别。
- 入口文件识别。
- 基础模块划分。
- 基础接口调用链候选识别。
- 登录认证流程候选识别。
- 状态管理逻辑候选识别。
- Repo Map 生成。
- 技术栈展示。
- 文件树展示。
- 模块树展示。
- 项目概览展示。
- 模块详情展示。
- 分析目标输入区域。
- Planner 计划展示。
- Skill Registry 选择结果。
- Context Snapshot 展示。
- 结构化项目解读报告。
- Trace Logger 执行轨迹。
- 已读取文件列表。
- 工具调用记录。
- 项目地图、模块说明、关键入口、阅读路线和调用链候选报告。
- 片段级 evidence 展示。
- 已读取文件展示。
- 推荐追问展示。

## MVP UI 范围

MVP UI 包括：

- 项目选择入口。
- 扫描进度展示。
- 技术栈识别结果。
- 文件树。
- 模块树。
- 项目概览卡片。
- 模块详情。
- 分析目标输入框。
- Planner 计划展示。
- Skill Registry 选择结果。
- Context Snapshot 展示。
- 结构化项目解读报告。
- Trace Logger 展示。
- 已读取文件列表。
- 工具调用记录。

## MVP 后端能力

- 提供本地 FastAPI 服务。
- 校验项目路径。
- 扫描目录，过滤常见无关目录，例如 `node_modules`、`.git`、`dist`。
- 读取配置文件。
- 生成基础 Repo Map。
- 返回分析计划、上下文快照、结构化报告和 trace events 给前端展示。

Phase 1 最小后端扫描闭环先实现：

- `POST /api/projects/scan` 接收本地项目路径。
- 校验路径存在且是目录。
- 只读扫描文件树摘要，不运行被扫描项目命令。
- 读取根目录 `package.json`，提取 scripts、dependencies、devDependencies。
- 读取 `pom.xml`、`build.gradle`、`settings.gradle` 等 Java 项目配置的基础摘要。
- 识别 package manager、Vue/Vite/TypeScript/Pinia/Vue Router/Axios/Element Plus 等标签。
- 识别 Java、Maven、Gradle、Spring Boot、Spring Web、Spring Security、MyBatis/JPA、JUnit 等标签。
- 识别 `src/main.ts`、`src/App.vue`、`src/router/index.ts`、`vite.config.ts` 等基础入口文件。
- 识别 `src/main/java/**/Application.java`、`src/main/resources/application.yml`、`src/main/resources/application.properties`、`pom.xml`、`build.gradle` 等 Java 入口和配置文件。
- 返回 warnings，例如 Vue 项目缺少 `package.json`、Java 项目缺少构建配置或配置解析失败。

持久化任务事件流、持久化扫描历史、完整多 Agent 并发、Reviewer 校验和精准 AST 级调用链仍属于后续步骤。

## MVP Agent 能力

MVP 的主目标不是普通 Ask 问答，而是围绕用户目标生成结构化代码库理解报告。默认目标包括：

- 项目地图。
- 模块说明。
- 关键入口。
- 阅读路线。
- 调用链候选。
- evidence 和不确定点。

最小 Skill Registry 会根据技术栈选择：

- `CodebaseOverviewSkill`：项目总览、模块和阅读路径。
- `VueSkill`：Vue/Vite 入口、路由、页面和组件候选。
- `SpringBootSkill`：Java/Spring Boot 入口、Controller、Service、Repository 和配置候选。

MVP 后续增强问题：

- 接口调用链在哪里？
- 登录认证流程怎么实现？
- 状态管理逻辑在哪里？

回答要求：

- 尽量基于已读取文件。
- 展示依据文件路径。
- 尽量展示行号和片段摘录。
- 暴露已读取文件和工具调用记录。
- 不确定时明确说明。
- 不编造未读取文件里的实现细节。

## MVP 不做什么

- 不自动修改代码。
- 不自动运行项目命令。
- 不自动提交 Git。
- 不做完整 AST 图谱。
- 不做云端账号系统。
- 不做桌面端打包。
- 不支持所有语言和框架，第一步只支持 Vue 和 Java 的常见项目结构。
- 不实现复杂多 Agent 并发编排或持久化任务队列。

## 验收标准

- 能输入一个公开 GitHub 仓库链接；本地 Vue / Java 项目路径只作为内部扫描契约保留。
- 能扫描文件树。
- 能读取 `package.json`。
- 能读取 Java 构建配置。
- 能识别 Vue、Vite、TypeScript、Pinia、Vue Router、Axios 等依赖。
- 能识别 Java、Maven、Gradle、Spring Boot 等依赖和结构。
- 能生成基础 Repo Map。
- 能在 UI 中展示技术栈、文件树、模块树。
- 能点击模块查看说明和关键文件。
- 能返回 `task_id`、`analysis_goal`、`analysis_plan`、`selected_skills`、`context_snapshot`、`report` 和 `trace_events`。
- 能展示 Planner 计划、Skill Registry、Context Snapshot、结构化项目解读报告、Trace Logger 和依据文件。
