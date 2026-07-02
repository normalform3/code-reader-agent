# CodeReader Agent

CodeReader Agent 是一个面向陌生代码库的本地可视化理解 Agent，能够自动扫描项目、生成模块地图、追踪关键流程，并通过接近桌面端 Coding Agent 的界面帮助开发者快速完成项目 onboarding。

它不是完整复刻 Claude Code 或 Codex 的自动编码系统，也不是普通的代码 RAG 问答工具。第一阶段重点是扫描陌生 GitHub 项目或本地项目、生成结构化 Repo Map、可视化展示模块关系和关键流程，并基于真实代码证据回答用户关于项目结构、入口、接口调用链、登录认证流程、状态管理逻辑和阅读路径的问题。

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

CodeReader Agent 的目标是把这些理解过程结构化、可视化，并尽量让每个结论都能追溯到文件路径、代码片段或工具调用记录。

## 项目目标

- 自动扫描陌生 GitHub 项目或本地代码仓库。
- 识别技术栈、目录结构、包管理器、启动命令和入口文件。
- 生成结构化 Repo Map。
- 识别核心模块、接口调用链、登录认证流程和状态管理逻辑。
- 按模块、文件、入口、调用链和证据片段可视化展示项目。
- 支持用户围绕代码库继续提问。
- 通过工具调用、skills、上下文管理和多 Agent 协作完成代码理解任务。
- 展示 Agent 使用过的 skill、工具调用和证据来源。
- 生成简单 onboarding 总结文档。

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

第一版先支持 Vue 和 Java 项目的本地只读理解闭环：

- 输入或选择本地项目路径。
- 扫描文件树。
- 读取 `package.json`、`pom.xml`、`build.gradle`、`settings.gradle` 等基础配置。
- 识别 Vue、Vite、TypeScript、Pinia、Vue Router、Axios、Element Plus 等前端依赖。
- 识别 Java、Maven、Gradle、Spring Boot、常见 Web/API/ORM/测试依赖。
- 识别启动命令、构建命令和入口文件。
- 识别 Vue 应用入口、路由、store、请求封装和页面目录。
- 识别 Java 应用入口、包结构、Controller、Service、Repository、配置文件和测试目录。
- 自动划分基础模块。
- 生成结构化 Repo Map。
- 在 Web UI 中展示技术栈、文件树、模块树、项目概览、模块详情、Agent 对话、已读取文件和工具调用记录。
- 支持回答：
  - 这个项目是干什么的？
  - 这个项目怎么运行？
  - 我应该从哪些文件开始看？
- 逐步支持回答：
  - 接口请求链路在哪里？
  - 登录认证流程怎么走？
  - 状态管理逻辑在哪里？
- 支持展示回答依据文件路径。
- 支持生成简单 onboarding 总结。

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
- Skill Router：根据用户问题选择项目总览、启动分析、登录流程、接口链路、页面数据来源等分析 skill。
- Read-only Tools：第一版工具默认只读，任何写文件或运行命令的能力都需要用户确认。
- Agent Panel：展示回答、当前 skill、读取文件、工具调用和后续问题建议。
- Codebase Map：展示模块树、文件树和后续的模块关系图。

## 技术栈

后端与 Agent Runtime：

- Python
- FastAPI
- Pydantic
- LiteLLM（规划中，当前不接入真实 LLM provider）
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

当前仓库已包含本地 API、项目扫描和确定性项目解读的早期实现；完整 Repo Map Builder、Web UI、事件流和多 Agent 协作仍在后续阶段。

后续 Phase 1 计划：

```bash
# 启动本地 API
uvicorn apps.api.main:app --reload

# 启动 Web UI
cd apps/web
npm install
npm run dev
```

用户在 Web UI 中输入本地项目路径后触发扫描，并查看 Repo Map 和 Agent 解释。

## 当前开发进度

项目当前处于 Phase 0 到 Phase 1 的过渡阶段，已经完成了规划文档、基础目录结构、本地 API 雏形、项目扫描能力、确定性 Repo Map Builder 初版，以及 React/Vite Web UI 的最小闭环。

已经具备的能力：

- 后端提供本地 FastAPI 服务入口。
- 能读取本地项目路径并执行只读扫描。
- 能识别基础文件树、技术栈线索、入口文件、包管理器和构建配置。
- 已有确定性的 Repo Map 数据结构和 Builder 初版。
- Web UI 已支持输入本地项目路径、触发扫描、展示技术栈、入口文件、模块卡片、模块详情、工具调用、证据和提醒。
- Agent 项目解读目前以确定性解释为主，支持回答项目用途、运行方式和建议阅读路径。
- Agent 解释已支持最小 Skill Router，可路由到项目总览、运行方式和前端结构分析。
- Repo Map 和 Agent 解释已支持片段级 evidence、已读取文件和工具调用记录。
- 已有基础测试覆盖扫描、Repo Map、解释器和 API 行为。

尚未完成的能力：

- 尚未接入真实 LLM provider。
- 尚未实现完整 Agent Loop、多 Agent 协作和 Reviewer 校验。
- 尚未实现复杂代码图谱、全量 AST 分析或跨文件调用链追踪。
- Web UI 仍是 MVP 工作台，模块关系图、事件流和更完整的证据查看还需要继续补齐。
- 当前重点仍是本地只读理解，不支持自动修改代码或自动提交 Git。

## 接下来的开发计划

短期优先级：

1. 稳定扫描与 Repo Map：补齐 Vue/Vite/TypeScript 和 Java/Spring 项目的基础识别规则，保证输出结构稳定。
2. 完善 Web UI：增加文件树、模块树、扫描进度、空状态、错误状态和证据详情，让本地理解闭环更清楚。
3. 强化证据追踪：让每个模块、入口、运行命令和回答结论都能关联到明确文件路径或配置来源。
4. 扩展确定性解释能力：先用普通代码回答“项目做什么”“怎么运行”“从哪里开始读”等高频问题。
5. 增加最小 Skill Router：在不引入复杂 Agent Loop 的前提下，按问题类型选择项目总览、运行方式、阅读路径等分析 skill。

中期计划：

1. 引入可选 LLM：只用于总结、分类、模糊理解和结构化解释，确定性扫描、过滤和校验仍由普通代码完成。
2. 增加 Reviewer 校验：检查回答是否有证据支撑、是否遗漏重要文件、是否出现过度猜测。
3. 增加 API 流程、登录认证流程、状态管理逻辑等专题分析。
4. 增强 Codebase Map 可视化：展示模块关系、关键文件、入口和证据链。
5. 持续补充测试，优先覆盖 Repo Map Schema、扫描规则和 API 契约。

## Roadmap

- Phase 0：项目规划、文档、目录结构、初始 Python 包。
- Phase 1：本地 API 服务、项目扫描、Vue/Java 技术栈识别。
- Phase 2：Repo Map Schema 与 Builder。
- Phase 3：Web UI 原型，展示文件树、模块树、项目概览。
- Phase 4：项目总览问答与 onboarding 总结。
- Phase 5：Skills 机制，支持登录流程、API 流程、页面数据来源和 Java 分层结构分析。
- Phase 6：多 Agent 协作、Reviewer、证据追踪。
- Phase 7：Codebase Map 可视化增强。
- Phase 8：TUI 或桌面端体验优化。
- Phase 9：支持更多技术栈和真实项目 demo。

## 简历导向描述

CodeReader Agent：面向陌生代码库的本地可视化理解 Agent

基于 FastAPI + React + LiteLLM 构建本地 Codebase Onboarding Agent，支持自动扫描陌生 Vue / Java 代码仓库、识别技术栈与目录结构、构建 Repo Map，并将项目按模块、文件、入口、调用链和证据片段进行可视化展示。系统通过 Planner、Explorer、Analyzer、Writer、Reviewer 多 Agent 协作流程，结合 `list_files`、`read_file`、`search_code`、`detect_framework`、`extract_symbols`、`trace_api_flow` 等工具完成代码理解任务；设计 Skill Router 支持项目总览、登录认证流程、接口调用链、状态管理逻辑、Java 分层结构等分析场景。前端提供接近桌面端 Coding Agent 的交互体验，支持模块地图、文件树、Agent 对话、工具调用过程和证据追踪，帮助开发者快速理解陌生项目。
# code-reader-agent
