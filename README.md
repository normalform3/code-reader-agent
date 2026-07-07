# CodeReader Agent

CodeReader Agent 是一个面向陌生 Java Web / 前后端项目的代码库理解 Agent。它的核心目标不是替代开发者写代码，而是先生成结构化项目理解报告，再提供类似 GitHub Copilot Ask 的右侧追问模式，帮助用户围绕真实代码证据继续理解项目。

一句话定位：

> CodeReader Agent 是一个面向 Java Web / 前后端项目的代码库理解 Agent，能够先生成项目地图、模块说明、关键入口和阅读路线，再把报告沉淀为 Project Memory，支持基于项目记忆和只读工具的 Ask 模式追问。

它和通用 Coding Agent 的区别是：CodeReader Agent 当前不自动改代码，而是把重点放在“先把陌生代码库整理成可导航、可追踪、可复用的知识结构”，再在 Ask 模式中像 Copilot Ask 一样回答局部问题，但回答必须优先检索项目记忆并按需调用只读工具补证据。

## 项目背景

开发者接手一个陌生 GitHub 项目时，通常需要先回答这些问题：

- 项目使用什么技术栈？
- 应该怎么启动和构建？
- 入口文件在哪里？
- 目录结构如何划分？
- 核心模块有哪些？
- 接口调用链在哪里？
- 登录认证流程如何实现？
- 状态管理逻辑在哪里？
- 哪些文件最值得先看？
- Agent 的解释是否真的来自代码证据？

CodeReader Agent 的目标是把这些理解过程变成两阶段工作流：第一阶段先 plan、调用工具、组织上下文并输出结构化报告；第二阶段进入 Ask 模式，先识别问题意图、检索项目记忆，再按需调用只读工具读取真实代码，并让每个结论都能追溯到文件路径、代码片段或工具调用记录。

## 项目目标

- 用户输入公开 GitHub 仓库链接后创建分析任务。
- Planner 生成分析计划。
- Tool Executor 按计划调用只读工具扫描项目、读取配置、搜索代码并构建 Repo Map。
- Context Manager 管理项目上下文、任务上下文、符号上下文和当前记忆上下文。
- Skill Registry 根据技术栈选择 `SpringBootSkill`、`VueSkill` 或通用理解 skill。
- 识别技术栈、目录结构、包管理器、启动命令和入口文件。
- 生成结构化 Repo Map。
- 识别核心模块、接口调用链、登录认证流程和状态管理逻辑。
- Analyzer 和 Report Writer 输出项目地图、模块说明、关键入口、阅读路线、调用链候选和证据。
- Trace Logger 记录计划、工具调用、上下文更新和最终产物。
- 报告生成后沉淀 `ProjectMemory`，包含 Project Memory、Module Summary、File Summary、API Index 和 Flow Index。
- Ask 模式通过 Intent Classifier、Context Retriever、Tool Planner、Evidence Collector、Answer Composer 和 Memory Updater 回答追问，并更新 `SessionMemory`。

## 核心用户痛点

- 陌生项目入口不清晰，阅读顺序靠猜。
- 框架、路由、状态管理、请求封装散落在不同目录。
- 代码问答工具容易脱离真实文件证据。
- 传统文件树只能展示结构，不能解释模块职责和关键流程。
- 自动编码 Agent 能力很强，但对“先理解项目”这一环节的可视化支持不够集中。

## 产品形态

第一版采用本地 Web App：

- 后端：FastAPI 本地 API 服务。
- 前端：Vite + React + TypeScript Web UI。
- 用户通过浏览器访问 localhost。
- 后续再评估 Tauri 或 Electron 打包为桌面应用。

第一阶段不做完整桌面端打包，避免把复杂度放在分发和系统集成上。

## MVP 功能范围

第一版先支持公开 GitHub 上的 Vue/Vite 前端项目和 Java/Spring Boot Web 项目的只读理解闭环：

- 输入公开 GitHub 仓库链接；本地项目路径仅作为内部扫描契约和开发调试能力保留。
- 扫描文件树。
- 读取 `package.json`、`pom.xml`、`build.gradle`、`settings.gradle` 等基础配置。
- 识别 Vue、Vite、TypeScript、Pinia、Vue Router、Axios、Element Plus 等前端依赖。
- 识别 Java、Maven、Gradle、Spring Boot、常见 Web/API/ORM/测试依赖。
- 识别启动命令、构建命令和入口文件。
- 识别 Vue 应用入口、路由、store、请求封装和页面目录。
- 识别 Java 应用入口、包结构、Controller、Service、Repository、配置文件和测试目录。
- 自动划分基础模块。
- 生成结构化 Repo Map。
- 在 Web UI 中展示技术栈、文件树、模块树、项目概览、模块详情、分析计划、Skill Registry、Context Snapshot、Report 和 Trace Logger。
- 输出结构化项目解读报告：
  - 项目地图。
  - 模块说明。
  - 关键入口。
  - 阅读路线。
  - 调用链候选。
  - evidence 和不确定点。
- 报告生成后提供右侧 Ask 边栏：
  - 支持项目总览、模块解释、文件解释、调用链、接口、配置和技术栈问题意图。
  - 优先检索 Project Memory、Module Summary、File Summary、API Index 和 Flow Index。
  - 上下文不足时调用只读工具读取文件、搜索关键词、解析依赖、路由、API 调用、Controller 和 Mapper 候选。
  - 回答包含相关文件、候选实现路径、关键代码说明和参考依据。

## 非目标范围

第一阶段明确不做：

- 自动大规模修改代码。
- 自动提交 Git。
- 云端多用户系统。
- 插件市场。
- 完整 IDE 插件。
- 桌面端打包。
- 多语言项目全面支持。
- 复杂代码图谱引擎。
- 高精度全量 AST 分析。
- 自动修复 bug。
- 企业级账号和权限系统。

## 核心特性

- Repo Map：把项目结构、模块、文件角色、依赖、入口和证据保存为结构化数据。
- Evidence Tracking：回答必须尽量引用已读取文件、路径和片段，避免凭空猜测。
- Skill Registry：根据项目技术栈选择 `SpringBootSkill`、`VueSkill` 或通用理解 skill。
- Planner / Context / Report / Trace：让用户看到分析计划、上下文选择、最终报告和执行轨迹。
- Read-only Tools：第一版工具默认只读，任何写文件或运行命令的能力都需要用户确认。
- Agent Panel：展示分析目标、Planner 计划、Skill Registry、Context Snapshot、Report、Agent Steps 和 Trace Logger。
- Codebase Map：展示模块树、文件树和后续的模块关系图。

## 技术栈

后端与 Agent Runtime：

- Python
- FastAPI
- Pydantic
- LangGraph（Ask 模式节点编排；本地依赖不可用时 runtime 使用同顺序 fallback 以便离线测试）
- LiteLLM（通过百炼 OpenAI-compatible 接口接入 `glm-5.1`，缺少环境变量时自动降级）
- SQLite（规划中）
- ripgrep（规划中，通过 subprocess 调用）
- pytest

前端与可视化：

- React
- Vite
- TypeScript
- Tailwind CSS
- shadcn/ui
- React Flow
- Monaco Editor（后续）
- Markdown Renderer
- SSE 或 WebSocket

## 基础使用方式草案

当前仓库已包含本地 API、公开 GitHub 导入、项目扫描、Repo Map Builder、确定性项目解读、最小只读 LLM tool loop、结构化报告字段、Project Memory、Ask 模式 API 和 React/Vite Web 工作台。

后续 Phase 1 计划：

```bash
# 启动本地 API
uvicorn apps.api.main:app --reload

# 启动 Web UI
cd apps/web
npm install
npm run dev
```

用户在 Web UI 中输入公开 GitHub 仓库链接后，系统会把仓库导入到本地只读缓存，再触发扫描、生成 Repo Map 和项目说明书。报告生成后，右侧 Ask 边栏会调用 `/api/agent/ask` 进行追问，不再把每轮问题都当成整份报告重新生成。

## 当前开发进度

项目当前已经进入“项目理解 + Ask 模式”MVP 阶段：公开 GitHub 导入、只读扫描、Repo Map、结构化报告、Project Memory、Ask 意图分类、只读补证据、Session Memory 和 React/Vite Web UI 已形成闭环。

已经具备的能力：

- 后端提供本地 FastAPI 服务入口。
- 能读取本地项目路径并执行只读扫描。
- 能导入公开 GitHub 仓库到本地只读缓存，并复用现有扫描流程分析。
- 能识别基础文件树、技术栈线索、入口文件、包管理器和构建配置。
- 已有确定性的 Repo Map 数据结构和 Builder 初版。
- Web UI 已支持输入公开 GitHub 仓库链接、触发导入和分析、展示技术栈、入口文件、模块卡片、模块详情、分析计划、技能选择、上下文快照、结构化报告、工具调用、trace、证据和提醒。
- Agent 项目解读支持可选 LLM tool loop；LLM 不可用时仍输出完整 plan、context、report 和 trace。
- `/api/agent/run` 会返回并保存 `project_memory`；`/api/agent/ask` 会返回 intent、answer、related files、implementation path、references、tool calls、trace events 和 session memory。
- Agent 解释已支持最小 Skill Registry，可按检测到的栈选择 `CodebaseOverviewSkill`、`VueSkill` 和 `SpringBootSkill`。
- Repo Map 和 Agent 解释已支持片段级 evidence、已读取文件和工具调用记录。
- 已有基础测试覆盖扫描、Repo Map、解释器、Ask 模式和 API 行为。

尚未完成的能力：

- 真实 LLM provider 已封装为可选模型层，当前默认使用百炼 `glm-5.1`，通过 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL` 读取系统环境变量。
- 尚未实现持久化任务队列、SSE 事件流、完整多 Agent 并发和 Reviewer 校验。
- 尚未实现复杂代码图谱、全量 AST 分析或跨文件调用链追踪。
- Web UI 仍是 MVP 工作台，模块关系图、事件流和更完整的证据查看还需要继续补齐。
- 当前重点仍是本地只读理解，不支持自动修改代码或自动提交 Git。

## 接下来的开发计划

短期优先级：

1. 稳定 Ask 模式：继续增强 7 类意图分类、Context Retriever 和 Tool Planner。
2. 扩充 Project Memory：提高 API Index、Flow Index、File Summary 的覆盖面。
3. 完善 Web UI：让 Ask trace、工具调用、证据和 Session Memory 更清楚。
4. 强化证据追踪：让每个模块、入口、运行命令和 Ask 回答都能关联到明确文件路径或配置来源。
5. 扩展专项 skill：逐步增强 Spring Boot 分层结构、Vue 页面结构、API 调用链候选和认证流程候选。

中期计划：

1. 稳定可选 LLM：继续把模型层限制在总结、分类、模糊理解和结构化解释，确定性扫描、过滤和校验仍由普通代码完成。
2. 增加 Reviewer 校验：检查回答是否有证据支撑、是否遗漏重要文件、是否出现过度猜测。
3. 增加 API 流程、登录认证流程、状态管理逻辑等专题分析。
4. 增强 Codebase Map 可视化：展示模块关系、关键文件、入口和证据链。
5. 持续补充测试，优先覆盖 Repo Map Schema、扫描规则和 API 契约。

## Roadmap

- Phase 0：项目规划、文档、目录结构、初始 Python 包。
- Phase 1：本地 API 服务、项目扫描、Vue/Java 技术栈识别。
- Phase 2：Repo Map Schema 与 Builder。
- Phase 3：Web UI 原型，展示文件树、模块树、项目概览。
- Phase 4：可信理解闭环，包含 evidence、只读工具和基础工作台。
- Phase 5：目标驱动项目理解报告，包含 Planner、Skill Registry、Context Snapshot、Report Writer 和 Trace Logger。
- Phase 6：Ask 模式，包含 Project Memory、Intent Classifier、Context Retriever、Tool Planner、Evidence Collector、Answer Composer 和 Session Memory。
- Phase 7：专项 Skills 与 Reviewer，支持登录流程、API 流程、页面数据来源和 Java 分层结构分析。
- Phase 8：Codebase Map 可视化增强。
- Phase 9：TUI / 桌面端体验优化和更多真实项目 demo。

## 简历导向描述

CodeReader Agent：面向陌生 Java Web / 前后端项目的代码库理解 Agent

基于 FastAPI + React + LangGraph + LiteLLM 构建本地 Codebase Understanding Agent，支持导入公开 GitHub 仓库、识别 Vue/Vite 与 Java/Spring Boot 技术栈、构建 Repo Map，并生成项目地图、模块说明、关键入口、阅读路线、调用链候选和证据报告。报告会沉淀为 Project Memory，右侧 Ask 模式通过意图分类、上下文检索、只读工具补证据和 Session Memory 支持连续追问，帮助开发者快速接手陌生项目。
# code-reader-agent
