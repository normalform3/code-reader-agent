# CodeReader Agent 项目计划

## 项目愿景

CodeReader Agent 希望成为一个本地可视化 Codebase Onboarding Agent。用户打开一个陌生 GitHub 项目或本地项目后，它能自动扫描代码仓库，识别技术栈、目录结构、入口文件、核心模块、接口调用链、登录认证流程和状态管理逻辑，构建结构化 Repo Map，并通过可视化界面把项目按模块、文件、入口、调用链和证据片段展示出来。

它的核心目标不是自动替用户改代码，而是先帮助用户真正理解代码。

## 核心用户痛点

- 陌生项目缺少清晰入口。
- 启动命令、框架依赖、路由、状态管理、请求封装、登录认证和后端分层结构分散在不同文件。
- 普通代码问答缺少可视化结构和证据追踪。
- 大模型容易根据文件名或经验猜测，难以证明结论来自真实代码。
- 开发者需要一个能快速生成 onboarding 路径的本地工具。

## 产品定位

CodeReader Agent 是本地可视化理解 Agent：

- 本地运行，优先分析用户已有项目目录。
- 使用 Repo Map 作为结构化项目地图。
- 使用 tools 和 skills 组织分析过程。
- 使用 evidence 机制约束 Agent 回答。
- 使用 Web UI 展示模块、文件、工具调用和证据。
- 第一阶段优先支持 Vue 和 Java 项目，先跑通前端单页应用与 Java Web 后端项目的理解闭环。

## Phase 0：项目规划与文档准备

功能清单：

- 建立项目目录结构。
- 创建核心设计文档。
- 创建初始 Python 包结构。
- 创建 `pyproject.toml`。
- 明确 MVP、非目标、架构、UI、Repo Map、tools、skills、context manager 和多 Agent 协作。

验收标准：

- 文档覆盖项目定位、架构和 MVP 边界。
- 仓库中存在后续实现所需的基础目录。
- 不要求提供完整可运行产品；当前仓库已有扫描 API 和确定性项目解读 API 的早期实现，后续计划以此为基础继续收敛。

## Phase 1：本地 API 服务与项目扫描

功能清单：

- 创建 FastAPI 服务。
- 提供项目扫描 API。
- 扫描文件树。
- 读取 `package.json`。
- 识别包管理器、依赖、启动命令、构建命令。
- 识别 Vue / Vite / TypeScript / Pinia / Vue Router / Axios。
- 识别 Java / Maven / Gradle / Spring Boot。
- 识别基础目录结构、入口文件和配置文件。

验收标准：

- 用户能输入本地项目路径。
- API 能返回技术栈和文件树摘要。
- Vue 项目能识别前端入口、路由、状态管理和请求封装候选位置。
- Java 项目能识别应用入口、包结构、Controller、Service、Repository 和配置文件候选位置。
- 扫描过程有基础工具调用记录。

## Phase 2：Repo Map Schema 与 Builder

功能清单：

- 实现 Repo Map Pydantic models。
- 根据扫描结果生成基础模块树。
- 识别入口文件、重要文件、配置文件。
- 保存 Repo Map 到本地结构化存储。

验收标准：

- 给定 Vue/Vite 项目能生成基础 Repo Map。
- 给定 Java/Spring Boot 项目能生成基础 Repo Map。
- Repo Map 包含模块、文件、入口、依赖和证据。
- 回答时可以基于 Repo Map 选择上下文。

## Phase 3：本地 Web UI 原型

功能清单：

- 创建 Vite + React + TypeScript 前端。
- 实现项目选择入口。
- 展示扫描进度。
- 展示技术栈、文件树、模块树和项目概览。
- 展示工具调用记录和已读取文件。

验收标准：

- 用户可以在浏览器完成一次项目扫描。
- UI 能清楚展示 Repo Map 的主要字段。

## Phase 4：项目总览问答与 onboarding 总结

功能清单：

- 支持项目总览 skill。
- 支持启动方式分析 skill。
- 支持推荐阅读路径。
- 支持生成简单 onboarding 总结。
- 设计版本化单 Agent prompt。
- 在未接入真实 LLM 前提供确定性 fallback 解读。

验收标准：

- 能回答“这个项目是干什么的？”
- 能回答“这个项目怎么运行？”
- 能回答“我应该从哪些文件开始看？”
- 回答中展示依据文件路径。
- API 返回 prompt version、prompt messages、evidence 和 warnings。
- 不把未读取源码内容伪装成证据。

## Phase 4.5：可信理解闭环

功能清单：

- 将 evidence 从路径级扩展为可选片段级，包含行号、摘录、收集工具和收集时间。
- 实现安全只读工具 `read_file` 和 `search_code`，默认拒绝敏感文件并防止路径穿越。
- 增加最小 Skill Router，支持项目总览、运行方式和前端结构三个确定性 skill。
- Web UI 展示文件树、重要文件、模块证据片段、已读取文件、工具调用、warnings 和推荐追问。
- 对登录/API 类问题只展示候选证据和不确定提示，不声称完成完整调用链。

验收标准：

- Vue 和 Java 示例项目仍能完成扫描、Repo Map 和确定性解释。
- API 返回兼容旧字段，并新增工具调用、已读取文件和片段 evidence。
- UI 能让用户看到 Agent 读取了哪些文件、依据了哪些片段、哪些结论不确定。
- `python -m pytest`、`python -m compileall src apps` 和前端 build 通过。

## Phase 5：专项 Skills

功能清单：

- 登录认证流程分析。
- API 请求链路分析。
- 页面数据来源分析。
- 状态管理分析。
- Java 分层结构分析。

验收标准：

- 每个 skill 有明确触发条件、搜索关键词、读取文件和输出格式。
- 回答能区分代码证据和不确定推测。

## Phase 6：多 Agent 协作与 Reviewer

功能清单：

- Planner、Explorer、Analyzer、Writer、Reviewer 协作。
- Agent State 和 Tool Call 可视化。
- Reviewer 检查证据完整性和过度猜测。

验收标准：

- UI 能展示当前 skill、Agent 步骤、工具调用和证据。
- Reviewer 能标记缺少证据的结论。

## Phase 7：Codebase Map 可视化增强

功能清单：

- 模块关系图。
- 调用链图。
- 页面到 API 的数据流图。
- 登录认证流程图。

验收标准：

- 关键流程能以图形方式展示。
- 图中节点可以追溯到文件和证据。

## 最终简历展示效果

项目最终应展示为一个真实可用的本地 Codebase Onboarding Agent：开发者打开一个陌生 Vue 或 Java 项目后，系统能自动扫描代码仓库、生成 Repo Map、可视化模块结构、追踪关键流程，并通过 evidence-grounded Agent 对话帮助用户快速理解项目。
