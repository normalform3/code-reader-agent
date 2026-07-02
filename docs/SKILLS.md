# Skills 机制

## 设计目标

Skill 用于把常见代码理解任务固化为可复用流程。Planner Agent 根据用户问题选择 skill，Explorer Agent 按 skill 的关键词和文件优先级收集证据，Analyzer 和 Writer 再生成结构化回答。

每个 skill 都需要定义：

- 适用场景。
- 触发条件。
- 优先搜索关键词。
- 优先读取文件。
- 可用 tools。
- 上下文选择策略。
- 输出格式。
- 验证方式。
- 失败处理方式。

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
