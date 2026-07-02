# MVP 范围

## MVP 目标

第一版目标是跑通一个最小但完整的本地代码库理解闭环：

用户输入一个本地 Vue 或 Java 项目路径后，CodeReader Agent 能扫描项目、识别技术栈、生成基础 Repo Map，并在 Web UI 中展示结构化结果和基于证据的回答。

当前 MVP 支持范围：

- Vue：优先覆盖 Vue3 / Vite / TypeScript 项目，识别路由、状态管理、请求封装和页面目录。
- Java：优先覆盖 Maven / Gradle / Spring Boot 项目，识别应用入口、包结构、Controller、Service、Repository、配置文件和测试目录。

当前实现已跑通 Phase 1-4 最小闭环：本地扫描、基础 Repo Map、React/Vite 工作台、确定性项目解读和基础测试。下一步属于 Phase 4.5，重点不是扩展语言或接入真实 LLM，而是提升 evidence 粒度、只读工具安全性和 UI 可验证性。

## MVP 用户流程

1. 用户打开本地 Web UI。
2. 用户输入一个本地项目路径。
3. 后端扫描文件树。
4. Vue 项目读取 `package.json` 和关键配置。
5. Java 项目读取 `pom.xml`、`build.gradle`、`settings.gradle` 等构建配置。
6. 系统识别技术栈、启动命令和入口文件。
7. 系统生成基础 Repo Map。
8. UI 展示技术栈、文件树、模块树、项目概览和工具调用记录。
9. 用户提问项目总览、运行方式或阅读顺序。
10. Agent 基于已读取文件回答，并展示依据文件。
11. 用户继续追问接口调用链、登录认证流程或状态管理逻辑。
12. 用户生成简单 onboarding 总结。

## MVP 功能列表

- 本地项目路径输入。
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
- Agent 对话区域。
- 已读取文件列表。
- 工具调用记录。
- 简单 onboarding 总结。
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
- Agent 对话框。
- 当前使用 skill 展示。
- 已读取文件列表。
- 工具调用记录。
- onboarding 总结展示。

## MVP 后端能力

- 提供本地 FastAPI 服务。
- 校验项目路径。
- 扫描目录，过滤常见无关目录，例如 `node_modules`、`.git`、`dist`。
- 读取配置文件。
- 生成基础 Repo Map。
- 提供任务事件给前端展示。

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

完整任务事件流、持久化扫描历史、真实 LLM provider 和多 Agent 编排仍属于后续步骤。

## MVP Agent 能力

MVP 只需要支持三类问题：

- 这个项目是干什么的？
- 这个项目怎么运行？
- 我应该从哪些文件开始看？

Phase 4.5 最小 Skill Router 会把问题确定性路由到：

- `project_overview_skill`：项目总览、模块和阅读路径。
- `setup_analysis_skill`：安装、启动、构建和测试命令候选。
- `frontend_analysis_skill`：Vue/Vite 入口、路由、页面和组件候选。

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
- 不实现复杂多 Agent 编排。

## 验收标准

- 能选择或输入一个本地 Vue 或 Java 项目路径。
- 能扫描文件树。
- 能读取 `package.json`。
- 能读取 Java 构建配置。
- 能识别 Vue、Vite、TypeScript、Pinia、Vue Router、Axios 等依赖。
- 能识别 Java、Maven、Gradle、Spring Boot 等依赖和结构。
- 能生成基础 Repo Map。
- 能在 UI 中展示技术栈、文件树、模块树。
- 能点击模块查看说明和关键文件。
- 能回答“这个项目是干什么的？”
- 能回答“这个项目怎么运行？”
- 能回答“我应该从哪些文件开始看？”
- 能展示回答依据文件。
- 能生成简单 onboarding 总结。
