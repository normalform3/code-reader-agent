# 技术决策记录

## 为什么第一版做只读理解型 Agent，而不是自动改代码 Agent

日期：2026-07-02

状态：Accepted

背景：项目核心价值是帮助开发者快速理解陌生代码库，而不是替代完整编码 Agent。

备选方案：

- 自动改代码 Agent。
- 只读理解型 Agent。

最终选择：只读理解型 Agent。

选择原因：只读理解更贴合 onboarding 场景，风险更低，更容易用 evidence 验证，也更适合第一版 MVP。

后续影响：第一版工具默认只读。任何写文件、运行命令或 Git 操作都需要用户确认。

## 为什么项目主形态从 CLI 调整为本地可视化 Web UI

日期：2026-07-02

状态：Accepted

背景：项目需要展示模块地图、文件树、Agent 对话、工具调用和证据。CLI 不适合承载这些并列信息。

备选方案：

- CLI-first。
- 本地 Web UI。
- 直接桌面应用。

最终选择：本地 Web UI。

选择原因：Web UI 能快速实现接近桌面端的交互体验，同时避免桌面打包复杂度。

后续影响：CLI 仅作为调试入口，产品主体验围绕 Web UI 设计。

## 为什么前端选择 React + Vite + TypeScript

日期：2026-07-02

状态：Accepted

背景：界面需要模块关系图、工作台布局、组件化面板、Markdown 渲染和后续 Monaco 代码预览。

备选方案：

- React + Vite + TypeScript。
- Vue3 + Vite + TypeScript。

最终选择：React + Vite + TypeScript。

选择原因：React Flow、shadcn/ui 和 Monaco 集成生态更适合当前规划的 Codebase Map 与工作台式界面。

后续影响：被分析目标项目第一版优先支持 Vue 和 Java，但产品自身前端使用 React。

## 为什么第一版优先支持 Vue 和 Java 项目

日期：2026-07-02

状态：Accepted

背景：项目最终定位是帮助开发者理解陌生 GitHub 项目。第一步既需要覆盖前端单页应用，也需要覆盖常见 Java 后端项目，才能展示接口调用链、登录认证流程、状态管理逻辑和模块地图的核心价值。

备选方案：

- 只支持 Vue3 / Vite。
- 同时支持大量框架和语言。
- 优先支持 Vue 和 Java。

最终选择：优先支持 Vue 和 Java。

选择原因：Vue/Vite 项目的入口、路由、状态管理和请求封装模式清晰，适合验证前端理解链路；Java/Spring Boot 项目的入口、分层结构、Controller/Service/Repository 和安全配置模式清晰，适合验证后端理解链路。两者组合能更好展示 CodeReader Agent 的最终定位，但仍比“支持所有语言”更克制。

后续影响：第一阶段实现 Vue 和 Java 的常见项目结构识别。React、Next.js、FastAPI、Express 和复杂多语言项目放到后续阶段。

## 为什么第一版不直接做桌面应用打包

日期：2026-07-02

状态：Accepted

背景：桌面打包会引入文件权限、进程管理、升级、跨平台兼容等复杂度。

备选方案：

- 直接 Tauri/Electron。
- 先做本地 Web UI。

最终选择：先做本地 Web UI。

选择原因：第一阶段价值在代码理解闭环，不在分发形态。

后续影响：桌面化保留为 Phase 8。

## 为什么需要 Repo Map

日期：2026-07-02

状态：Accepted

背景：如果只依赖自然语言总结，前端展示、上下文选择和证据校验都会变得困难。

备选方案：

- 临时问答上下文。
- 结构化 Repo Map。

最终选择：结构化 Repo Map。

选择原因：Repo Map 能统一服务 UI、Context Manager、Agent 回答和 Reviewer。

后续影响：Repo Map Schema 的变更必须同步更新 `docs/REPO_MAP_SCHEMA.md`。

## 为什么需要 skills 机制

日期：2026-07-02

状态：Accepted

背景：项目总览、登录流程、接口链路、页面数据来源等问题需要不同搜索策略和输出结构。

备选方案：

- 每次由模型自由规划。
- 使用 skills 固化常见任务流程。

最终选择：使用 skills 机制。

选择原因：skills 能提升稳定性、可解释性和可测试性。

后续影响：新增 skill 必须更新 `docs/SKILLS.md`。

## 为什么需要 Context Manager

日期：2026-07-02

状态：Accepted

背景：把整个代码库一次性塞给模型不可扩展，也容易造成噪声和幻觉。

备选方案：

- 全量上下文。
- 按任务选择上下文。

最终选择：Context Manager 按任务选择上下文。

选择原因：先构建索引，再基于 Repo Map 和 skill 选择文件，更可控也更容易展示证据。

后续影响：回答需要展示已使用上下文和 evidence。

## 为什么需要 Reviewer Agent

日期：2026-07-02

状态：Accepted

背景：代码理解回答的可信度取决于是否有证据支撑。

备选方案：

- Writer 直接输出。
- Reviewer 检查后输出。

最终选择：加入 Reviewer Agent。

选择原因：Reviewer 能检查缺少证据、遗漏关键文件和过度猜测。

后续影响：Agent 输出结构需要保留 review 结果。

## 为什么需要 Evidence Panel

日期：2026-07-02

状态：Accepted

背景：用户需要看到 Agent 读过什么、调用了什么工具、哪些结论不确定。

备选方案：

- 只展示最终回答。
- 展示 Execution / Evidence Panel。

最终选择：展示 Evidence Panel。

选择原因：证据面板能让本地代码理解工具更可信，也更接近 Coding Agent 工作台体验。

后续影响：工具调用和 evidence 需要作为一等数据结构保存。

## 为什么要避免把整个代码库一次性塞给模型

日期：2026-07-02

状态：Accepted

背景：大代码库上下文长、噪声多、成本高，并且无法清楚解释回答依据。

备选方案：

- 全量读取。
- 索引后按任务读取。

最终选择：索引后按任务读取。

选择原因：这种方式更稳定、更便宜，也更容易绑定 evidence。

后续影响：Context Manager 和 tools 必须支持渐进式读取。

## 为什么 Phase 4.5 先做可信理解闭环，而不是直接接入 LLM 或多 Agent

日期：2026-07-02

状态：Accepted

背景：项目已经具备扫描、Repo Map、确定性解释和 Web UI 的最小闭环，但 evidence 粒度、工具调用记录和 UI 可验证性还不够强。如果此时直接接入 LLM 或多 Agent，容易让产品看起来更智能，但用户仍然无法判断结论是否可信。

备选方案：

- 立即接入真实 LLM provider。
- 立即实现 Planner/Explorer/Analyzer/Writer/Reviewer 多 Agent。
- 先补可信理解闭环。

最终选择：先补可信理解闭环。

选择原因：片段级 evidence、安全只读工具、最小 Skill Router 和工作台式 UI 能直接提升用户信任，也能为后续 LLM 和 Reviewer 提供稳定输入。

后续影响：Phase 4.5 只做 Vue/Java 范围内的证据增强和确定性 skill，不扩语言、不做完整调用链图、不声称完成真实多 Agent。
