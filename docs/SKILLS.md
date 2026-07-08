# Skills 机制

## 设计目标

Skill 用于把常见代码理解任务固化为可复用流程。它不是单纯提示词，也不是让模型直接回答问题的快捷方式，而是面向特定技术栈的代码理解插件。

当前定义：

```text
Skill = 技术栈名称 + 激活条件 + 扫描函数 + 解析规则 + 索引构建逻辑 + 检索提示 + 回答提示词
```

MVP 中 Skill Registry 基于 Repo Map、依赖、文件结构和轻量只读解析激活 `JavaWebSkill`、`SpringBootSkill`、`MyBatisSkill`、`VueSkill`、`RestApiSkill` 等能力。Skill 扫描结果会沉淀到 ProjectMemory 的 Code Knowledge Index，再由 Analyzer、Report Writer 和 Ask 模式复用。

每个 skill 都需要定义：

- 适用场景。
- 激活条件和置信度。
- 扫描目标和只读工具边界。
- 解析规则。
- 输出到 Code Knowledge Index 的结构化字段。
- Ask query hints。
- Ask tool plan hints。
- Answer Composer 的回答组织提示。
- 验证方式。
- 失败处理方式。

## MVP Skill Registry

当前 `/api/agent/run` 的 `selected_skills` 和 `active_skills` 来自运行时 Skill Registry：

- `CodebaseOverviewSkill`：默认启用，负责项目地图、模块说明、关键入口和阅读路线。
- `JavaWebSkill`：识别 Controller、Service、Mapper/Repository、Entity/DTO/VO 分层。
- `SpringBootSkill`：识别 Spring Boot 启动类、配置、Controller 接口和安全配置。
- `MyBatisSkill`：识别 Mapper、XML、SQL、实体/表映射候选。
- `VueSkill`：识别 Vue 入口、路由、页面、组件、状态和 API 调用。
- `RestApiSkill`：识别前后端接口定义、调用和映射候选。
- `ApiFlowCandidateSkill` / `AuthFlowCandidateSkill`：兼容旧展示字段，用于标记 Repo Map 中已有 API/auth 候选。

MVP 不实现插件式动态 skill 加载，也不声称完成精准调用链追踪。

`active_skills` 会返回：

- skill 名称。
- 置信度。
- 激活原因。

## Code Knowledge Index 写入

Skill 扫描结果不会只生成自然语言报告，而是写入结构化索引：

- Java Web / Spring Boot：`file_summaries`、`module_summaries`、`symbol_index`、`api_index`、入口和配置文件。
- MyBatis：`data_model_index`、`mapper_relations`、Mapper/XML 文件和 SQL/table 候选。
- Vue：`route_index`、`frontend_api_call_index`、前端 File Summary 和 Symbol Index。
- REST API：合并后端 Controller endpoint 和前端 API call，补充 `api_index` 和 `flow_index` 候选。

这些索引统一存放在 `ProjectMemory` 中，版本字段为 `knowledge_index_version`。Ask 模式读到旧版 ProjectMemory 时会自动基于当前 Repo Map 重建索引。

## 两层轻量 Skill 路由

Skill Router 当前分为两层：

- 项目级 Skill 路由：首次扫描后，`SkillRegistry` 遍历内置 Skill，执行 `detect(repo_map)`，根据 matched、confidence 和 reason 生成 ActiveSkill。只有 ActiveSkill 会执行 `scan()` 并把结果写入 Code Knowledge Index。
- 问题级 Skill 路由：Ask 模式中，`SkillRouter` 只从 `ProjectMemory.active_skills` 中选择本轮相关 Skill。判断依据包括 intent、关键词、索引命中、resolved query 引用和 Session Memory 关注点。

当前保持轻量路由，不做复杂多 Agent 编排。这样可以减少上下文噪声和无效工具调用，同时保留可解释 trace 和确定性测试边界。后续可扩展为工具级路由和更复杂的 Skill 编排。

## Ask Intent 与 Skill 关系

Ask 模式先做问题意图分类，再选择上下文和只读工具。Skill 在 Ask 中只辅助上下文获取，不直接回答用户。

流程：

```text
Query Rewriter
-> Intent Classifier
-> SkillRouter 从 active skills 中选择 routed skills
-> Context Retriever 检索 Project Memory 和 Code Knowledge Index，并使用 routed skill query hints
-> Tool Planner 合并 routed skill tool plan hints
-> Evidence Collector 执行只读工具
-> Context Builder 合并 routed skill answer prompts
-> Answer Composer 基于 evidence 回答
```

当前支持 intent：

- `project_overview`：优先检索 Project Memory。
- `module_explanation`：检索 Module Summary、API Index 和相关 File Summary。
- `file_explanation`：定位 File Summary，必要时调用 `read_file`。
- `flow_trace`：检索 Flow Index，并读取关键文件补证据。
- `api_lookup`：检索 API Index，并调用 `parse_api_calls`、`parse_controller` 或 `search_keyword`。
- `config_lookup`：检索配置文件和依赖摘要，并调用 `parse_dependencies`。
- `tech_stack`：检索依赖文件和 Project Memory。
- `symbol_lookup`：检索 Symbol Index，并按需调用 `search_symbol`。

这些 intent 不替代技术栈 skill；intent 负责问题路由，Skill 负责决定哪些文件、关键词和证据更值得优先读取。

示例：用户问“登录功能是怎么实现的？”

- `SpringBootSkill` 可能提供 `AuthController`、`SecurityConfig`、`Jwt`、`UserDetailsService`。
- `JavaWebSkill` 可能提供 `AuthService`、`UserService`、`UserMapper`。
- `VueSkill` 可能提供 `Login.vue`、`auth.ts`、`src/api`。
- `RestApiSkill` 可能提供 `/login`、`/auth` 和前后端 API 搜索建议。

Tool Planner 再把这些 hints 转成只读工具计划。最终回答必须基于 `read_file`、`search_keyword`、`parse_controller`、`parse_api_calls` 等 evidence，而不是根据 Skill prompt 猜测。

前端 Skill 管理弹窗通过本地 registry API 展示和编辑 skill 元数据。该 registry 保存到 `.codereader/state.json`，也可以通过 `CODEREADER_STATE_DIR/state.json` 覆盖。

内置 skill：

- `CodebaseOverviewSkill`
- `VueSkill`
- `SpringBootSkill`
- `ApiFlowCandidateSkill`
- `AuthFlowCandidateSkill`
- `project_overview_skill`
- `setup_analysis_skill`
- `frontend_analysis_skill`

管理规则：

- registry item 字段包含 `name`、`description`、`notes`、`details`、`enabled` 和 `builtin`。
- `details` 是结构化详情分组，每组包含 `title` 和 `items`。
- 内置 skill 可以编辑说明、适用说明、结构化详情和启用状态。
- 内置 skill 不能真正删除；删除动作会将其禁用。
- 自定义 skill 支持新增、编辑和删除。
- 第一版自定义 skill 只进入管理弹窗 registry，不会自动参与 Agent 路由或 LLM tool loop。
- 内置 skill 的 `details` 来自当前 skill 文档和运行时边界，包含适用场景、触发条件、优先读取文件、可用 tools、输出格式、验证方式和失败处理。
- 旧 `.codereader/state.json` 中缺少 `details` 的内置项会在读取时自动补齐默认详情，同时保留用户编辑过的名称、说明、补充说明和启用状态。

管理 API：

- `GET /api/registry/skills`
- `POST /api/registry/skills`
- `PATCH /api/registry/skills/{skill_id}`
- `DELETE /api/registry/skills/{skill_id}`

## CodebaseOverviewSkill

适用场景：用户要求生成项目解读报告、项目地图、模块说明、关键入口和阅读路线。

输出格式：

- project manual。
- project map。
- module summaries。
- key entrypoints。
- reading route。
- call chain candidates。
- evidence。
- uncertainties。

当前实现：由 `code_reader_agent.runtime.analysis.build_project_manual` 和 `build_project_report` 基于 Repo Map 和 Agent 输出生成。首次分析返回 `project_manual` 和 `project_memory`，后续追问通过 `/api/agent/ask` 使用 Project Memory 和 Session Memory。

## project_overview_skill

适用场景：用户询问项目是做什么的、整体架构、主要模块。

触发条件：

- “这个项目是干什么的？”
- “介绍一下项目”
- “项目结构”

优先读取文件：

- `package.json`
- `pom.xml`
- `build.gradle`
- `settings.gradle`
- `README.md`
- `src/main.ts`
- `src/App.vue`
- `src/router/*`
- `src/main/java/**/*Application.java`
- `src/main/java/**/*Controller.java`
- `src/main/resources/application.*`

可用 tools：

- `list_files`
- `read_file`
- `read_config`
- `detect_framework`
- `build_repo_map`

输出格式：

- 项目用途。
- 技术栈。
- 核心模块。
- 入口文件。
- 推荐阅读路径。
- 依据文件。
- 不确定点。

验证方式：

- 检查结论是否引用配置或入口文件。

失败处理：

- 如果缺少 README 或 package 信息，说明只能基于文件结构推断。
- 如果缺少 Java 构建配置，说明只能基于目录和文件命名低置信度推断。

Phase 4 最小实现：

- `code_reader_agent.interpreter.interpret_project` 固定使用该 skill。
- 输入来自 `scan_project` 的确定性扫描结果。
- 输出 overview、setup summary、reading path、evidence 和 warnings。
- 同时生成 `project_interpreter_v1` prompt messages，后续可交给真实 LLM。
- 当前不读取 README 和源码全文，因此回答必须标明证据来自 package、文件树和入口文件扫描。

Phase 4.5 更新：

- `interpret_project` 不再固定只走该 skill，而是通过确定性 Skill Router 选择 project overview、setup analysis 或 frontend analysis。
- 该 skill 仍负责默认项目总览问题。
- 输出包含 `tool_calls`、`read_files` 和 `suggested_questions`。
- evidence 会尽量包含行号和片段摘录。

Prompt 设计：

- system prompt 定义 CodeReader Agent 的角色、证据边界和回答规则。
- user prompt 注入用户问题、扫描上下文、entrypoints、scripts、evidence paths 和 warnings。
- prompt 要求输出项目总览、启动方式、推荐阅读路径、依据文件和不确定点。
- prompt 不允许模型声称读取了没有读取过的文件内容。

## setup_analysis_skill

适用场景：用户询问如何运行、构建和开发。

触发条件：

- “怎么运行？”
- “启动命令”
- “怎么构建？”

优先读取文件：

- `package.json`
- `pom.xml`
- `build.gradle`
- `settings.gradle`
- `pnpm-lock.yaml`
- `yarn.lock`
- `package-lock.json`
- `vite.config.ts`
- `src/main/resources/application.yml`
- `src/main/resources/application.properties`

可用 tools：

- `read_config`
- `read_file`
- `detect_framework`

输出格式：

- 包管理器。
- Java 构建工具。
- 安装命令建议。
- dev/build/preview 命令。
- Maven/Gradle 启动和测试命令候选。
- 环境变量提示。
- 依据文件。

验证方式：

- 启动命令必须来自 `package.json` scripts。
- Java 启动命令必须来自 Maven/Gradle/Spring Boot 约定或构建配置，并明确标记为候选命令。

失败处理：

- 如果没有 scripts，说明未找到标准启动方式。

Phase 4.5 实现：

- 根据“怎么运行”“启动”“构建”“build”“run”“setup”等问题触发。
- 只基于 `package.json` scripts、包管理器 lockfile、Maven/Gradle/Spring Boot 约定和 Java 构建配置生成候选命令。
- Java 启动命令必须说明需要用户在本地确认。

## frontend_analysis_skill

适用场景：分析前端目录、组件、路由、页面。

触发条件：

- “前端结构”
- “页面在哪里”
- “组件如何组织”

优先搜索关键词：

- `createApp`
- `createRouter`
- `routes`
- `defineComponent`
- `setup`

优先读取文件：

- `src/main.ts`
- `src/App.vue`
- `src/router/*`
- `src/views/*`
- `src/components/*`

输出格式：

- 入口。
- 路由。
- 页面目录。
- 组件目录。
- 推荐阅读顺序。
- 依据文件。

Phase 4.5 实现：

- 根据“前端”“页面”“组件”“路由”“frontend”“router”等问题触发。
- 优先读取 `vite.config.*`、`src/main.*`、`src/App.vue`、`src/router/*`、`src/views/*`、`src/pages/*`、`src/components/*`。
- 输出前端阅读路径和证据片段。
- 不追踪完整页面到 API 数据流。

## auth_flow_skill

适用场景：分析登录认证流程。支持 Vue 前端认证链路和 Java/Spring Security 后端认证链路。

触发条件：

- “登录流程”
- “认证”
- “权限”
- “token”

优先搜索关键词：

- `login`
- `logout`
- `token`
- `auth`
- `permission`
- `beforeEach`
- `interceptor`
- `Authorization`
- `userStore`
- `router guard`
- `SecurityFilterChain`
- `WebSecurityConfigurerAdapter`
- `OncePerRequestFilter`
- `Jwt`
- `UserDetailsService`
- `AuthenticationManager`

优先读取文件：

- 登录页面。
- 用户 store。
- auth API 文件。
- request 封装文件。
- router 文件。
- Java Security 配置。
- 认证 Controller。
- token/JWT 工具类。
- 用户服务和权限模型。

输出格式：

- 涉及文件。
- 调用链。
- token 保存位置。
- 路由权限逻辑。
- 请求拦截逻辑。
- 后端认证入口、过滤器、用户加载、token 校验和权限配置。
- 证据文件。
- 不确定点。

验证方式：

- 检查是否读取了 router、store、request、login 页面或对应替代文件。

失败处理：

- 如果只找到部分证据，按已找到链路回答并标记缺口。

当前状态：

- Phase 4.5 暂不实现完整认证链路分析。
- 当用户询问登录、认证、权限或 token 时，只通过 `search_code` 返回候选文件和关键词证据，并明确标记尚未完成调用链追踪。

## api_flow_skill

适用场景：分析接口请求链路。支持 Vue 前端请求链路和 Java 后端接口链路。

触发条件：

- “接口请求”
- “API 怎么封装”
- “数据从哪里请求”

优先搜索关键词：

- `axios`
- `fetch`
- `request`
- `baseURL`
- `interceptors`
- `api`
- `@RestController`
- `@Controller`
- `@RequestMapping`
- `@GetMapping`
- `@PostMapping`
- `@PutMapping`
- `@DeleteMapping`
- `FeignClient`

优先读取文件：

- request 封装。
- API 目录。
- 页面调用 API 的文件。
- Java Controller。
- Java Service。
- Java Repository 或 Mapper。

输出格式：

- 请求库。
- 请求封装位置。
- API 模块。
- 调用链。
- Controller 到 Service 到 Repository/Mapper 的后端链路。
- 错误处理。
- 依据文件。

## page_data_flow_skill

适用场景：分析某个页面的数据来源。

触发条件：

- “这个页面的数据从哪里来？”
- “页面数据流”

优先搜索关键词：

- 页面组件名。
- `onMounted`
- `watch`
- `computed`
- `useStore`
- `api`
- `request`

优先读取文件：

- 页面文件。
- 相关 store。
- 相关 API 文件。
- request 封装。

输出格式：

- 页面入口。
- 数据获取位置。
- store 关系。
- API 调用。
- 渲染路径。
- 证据文件。

## state_management_skill

适用场景：分析状态管理。Vue 项目优先分析 Pinia/Vuex/store；Java 项目优先分析应用配置、会话、安全上下文和核心领域状态的持久化边界。

触发条件：

- “状态管理”
- “Pinia”
- “store”

优先搜索关键词：

- `defineStore`
- `pinia`
- `use`
- `state`
- `actions`
- `getters`
- `SecurityContextHolder`
- `HttpSession`
- `@ConfigurationProperties`
- `@Entity`
- `@Table`

优先读取文件：

- `src/stores/*`
- `src/store/*`
- `src/main.ts`
- 使用 store 的页面或组件。
- Java 配置类。
- Entity/domain 模型。
- Repository/Mapper。
- 认证或会话相关类。

输出格式：

- store 列表。
- 每个 store 的职责。
- 状态来源。
- 被哪些页面使用。
- Java 侧状态持久化或上下文边界。
- 依据文件。

## java_layered_architecture_skill

适用场景：分析 Java 项目的分层结构、包组织和核心模块。

触发条件：

- “Java 结构”
- “Spring Boot 结构”
- “Controller Service Repository”
- “后端模块”

优先搜索关键词：

- `@SpringBootApplication`
- `@RestController`
- `@Service`
- `@Repository`
- `@Mapper`
- `@Configuration`
- `@Entity`
- `@Component`

优先读取文件：

- `pom.xml`
- `build.gradle`
- `src/main/java/**/*Application.java`
- `src/main/java/**/*Controller.java`
- `src/main/java/**/*Service.java`
- `src/main/java/**/*Repository.java`
- `src/main/java/**/*Mapper.java`
- `src/main/resources/application.*`

输出格式：

- 应用入口。
- 包结构。
- Controller 列表。
- Service 列表。
- Repository/Mapper 列表。
- 配置文件。
- 核心业务模块候选。
- 依据文件。
- 不确定点。

验证方式：

- 至少引用应用入口或构建配置。
- 分层结论必须来自注解、文件路径或命名约定。

## onboarding_doc_skill

适用场景：生成新人导读文档。

触发条件：

- “生成 onboarding”
- “新人导读”
- “阅读指南”

优先读取文件：

- Repo Map。
- README。
- package 配置。
- 入口文件。
- 重要模块 evidence。

输出格式：

- 项目简介。
- 技术栈。
- 启动方式。
- 推荐阅读路径。
- 核心模块。
- 常见问题。
- 不确定点。

验证方式：

- Reviewer 检查是否引用 Repo Map 和 evidence。
