# Tool System

## 设计原则

第一版工具默认只读。CodeReader Agent 的核心任务是理解代码库，不是修改代码库。

任何写文件、运行命令、修改代码、Git 操作或删除文件的行为都必须先请求用户确认。

## 第一版工具

MVP 的工具由 Tool Executor 统一调用，并通过 `/api/agent/run` 的 `tool_calls` 和 `trace_events` 返回给前端。工具仍保持只读边界，不运行被分析项目命令，不写文件，不执行 Git 操作。

前端工具管理弹窗通过本地 registry API 展示和编辑工具元数据。该 registry 只保存 CodeReader 自己的 UI/配置状态，不会修改被分析仓库，也不会切换或重载当前项目工作台。

本地状态位置：

- 默认 `.codereader/state.json`
- 可用 `CODEREADER_STATE_DIR/state.json` 覆盖

内置工具：

- `import_github_repository`
- `scan_project`
- `build_repo_map`
- `read_file`
- `search_code`
- `search_keyword`
- `search_api_path`
- `list_files`
- `search_symbol`
- `parse_dependencies`
- `parse_routes`
- `parse_api_calls`
- `parse_controller`
- `parse_mapper`
- `detect_framework`
- `find_entrypoints`
- `generate_doc`

registry item 字段：

- `name`
- `description`
- `notes`
- `details`: 结构化详情分组，每组包含 `title` 和 `items`
- `enabled`
- `builtin`

内置工具可以编辑说明、结构化详情和启用状态，但不能真正删除；删除内置工具会把它标记为 disabled。自定义工具支持新增、编辑和删除。第一版自定义工具只进入管理弹窗 registry，不会自动进入 LLM tool whitelist。

内置工具的 `details` 来自当前工具文档和实现边界，包含用途、输入、输出、安全规则、实现位置和是否进入 LLM 白名单。旧 `.codereader/state.json` 中缺少 `details` 的内置项会在读取时自动补齐默认详情，同时保留用户编辑过的名称、说明、补充说明和启用状态。

管理 API：

- `GET /api/registry/tools`
- `POST /api/registry/tools`
- `PATCH /api/registry/tools/{tool_id}`
- `DELETE /api/registry/tools/{tool_id}`

### import_github_repository

用途：把公开 GitHub 仓库导入到本地只读缓存，作为后续扫描和 Repo Map 构建的项目目录。

输入：

- github_url

输出：

- project_name
- project_path
- github_url
- repository
- reused_cache
- warnings

安全规则：

- 第一版只支持 `https://github.com/owner/repo` 和 `.git` 形式的公开仓库链接。
- 不支持 private repo、token、任意 Git host 或任意 shell 命令。
- 使用参数列表调用 `git clone --depth 1`，不通过 shell 拼接命令。
- clone 后只允许走现有只读扫描、读文件和搜索工具。
- 不运行仓库内代码，不安装依赖，不执行 `npm install`、`mvn`、脚本或 Git hooks。
- 仓库快照缓存在本地 `.codereader/repos`，重复导入时可以复用缓存。

Phase 5.5 最小实现：

- 由 `code_reader_agent.github_importer.import_github_repository` 提供。
- API 入口为 `POST /api/projects/import-github`。
- 下载完成后，前端继续用返回的 `project_path` 调用现有 Repo Map 和 Agent API。

### list_files

用途：列出项目文件树。

输入：

- project_path
- ignore_patterns
- max_depth

输出：

- 文件和目录列表。
- 文件类型摘要。
- 忽略规则命中情况。

安全规则：

- 跳过 `.git`、`node_modules`、`dist`、`build` 等目录。

Phase 1 最小实现：

- 由 `code_reader_agent.scanner.scan_project` 在本地同步执行。
- 默认跳过 `.git`、`node_modules`、`dist`、`build`、`.venv`、`venv`、`coverage`、`__pycache__` 等目录。
- 只返回项目内相对路径、名称、类型和深度，不读取业务源码内容。

### read_file

用途：读取指定文件内容。

输入：

- project_path
- relative_path
- optional line range

输出：

- 文件内容。
- 行号。
- evidence id。

安全规则：

- 不读取明显包含密钥的文件，例如 `.env`，除非用户明确确认。
- 长文件需要截断或摘要。

Phase 4.5 实现：

- 由 `code_reader_agent.tools.read_only.read_file` 提供。
- 输入必须是项目内相对路径，禁止 `..` 越过项目根目录。
- 默认拒绝 `.env`、`.env.*`、私钥、证书、`.npmrc` 等敏感文件。
- 支持可选行号范围。
- 长片段默认截断并返回 warning。

### search_code

用途：搜索代码关键词。

输入：

- project_path
- query
- glob patterns

输出：

- 匹配文件。
- 行号。
- 片段。

实现建议：

- 优先调用 ripgrep。

Phase 4.5 实现：

- 由 `code_reader_agent.tools.read_only.search_code` 提供。
- 优先调用 `rg --fixed-strings --line-number`。
- 当 `rg` 不可用或调用失败时，使用 Python 文件遍历 fallback。
- 默认跳过 `.git`、`node_modules`、`dist`、`build`、虚拟环境和敏感文件。
- 无匹配时返回空列表，不作为错误处理。

### search_symbol

用途：搜索类名、函数名、组件名或方法名。

当前实现：

- 由 `code_reader_agent.tools.read_only.search_symbol` 提供。
- 复用 `search_code`，但限制在常见源码文件类型。
- 用于 Ask 模式在 File Summary 无法定位时补充查找。

### search_keyword

用途：按关键词搜索项目文件，可选粗粒度 scope。

当前实现：

- 由 `code_reader_agent.tools.read_only.search_keyword` 提供。
- 复用 `search_code` 的安全边界，可按 frontend、backend、config 等 scope 限制常见文件类型。
- 用于 Ask 模式补充模块、流程和实现细节证据。

### search_api_path

用途：搜索接口路径在哪里定义或调用。

当前实现：

- 由 `code_reader_agent.tools.read_only.search_api_path` 提供。
- 复用 `search_code`，限制在常见前端、后端和配置文件类型。
- 用于 Ask 模式的接口定位和调用位置问题。

### parse_dependencies

用途：解析依赖、脚本和 Java 配置摘要。

当前实现：

- 由 `code_reader_agent.tools.read_only.parse_dependencies` 提供。
- 复用 scanner 的 `package.json`、Maven、Gradle 和 Spring 配置解析。
- 用于技术栈、配置、启动方式类 Ask 问题。

### parse_routes

用途：轻量提取前端路由候选。

当前实现：

- 由 `code_reader_agent.tools.read_only.parse_routes` 提供。
- 通过正则读取 router/routes 文件中的 `path` 字段。
- 不做完整 AST 路由解析。

### parse_api_calls

用途：提取前端接口调用候选。

当前实现：

- 由 `code_reader_agent.tools.read_only.parse_api_calls` 提供。
- 提取 `axios`、`fetch`、`request` 的接口路径、方法、文件和行号候选。
- 结果用于 API Index 和 Ask 模式“接口在哪里被调用”问题。

### parse_controller

用途：提取 Spring Controller 接口候选。

当前实现：

- 由 `code_reader_agent.tools.read_only.parse_controller` 提供。
- 识别 `@GetMapping`、`@PostMapping`、`@RequestMapping` 等注解候选。
- 输出接口路径、HTTP 方法、后端文件和后端方法候选。

### parse_mapper

用途：提取 Mapper、Repository、DAO 和 XML 映射候选。

当前实现：

- 由 `code_reader_agent.tools.read_only.parse_mapper` 提供。
- 只输出候选文件和类型，不做 SQL 语义分析。

### read_config

用途：读取项目配置。

优先支持：

- `package.json`
- `pyproject.toml`
- `pom.xml`
- `vite.config.ts`
- `build.gradle`
- `settings.gradle`
- `application.yml`
- `application.properties`

MVP 重点支持 `package.json`、`pom.xml`、`build.gradle` 和 `settings.gradle`。

Phase 1 最小实现：

- 只读取项目根目录的 `package.json`。
- 提取 `name`、`version`、`scripts`、`dependencies`、`devDependencies`。
- `package.json` 缺失或格式异常时返回 warning，不让整个扫描崩溃。
- 只读取 Java 项目的根目录 `pom.xml`、`build.gradle`、`settings.gradle` 和常见 Spring 配置文件摘要。
- 提取 Java 构建工具、group/artifact/version、依赖坐标和常见插件。
- 扫描 API 通过 `java_build` 返回 Java 构建工具、项目坐标、依赖和配置文件列表。
- Java 配置缺失或格式异常时返回 warning，不让整个扫描崩溃。

### detect_framework

用途：识别技术栈。

输入：

- 配置文件内容。
- 文件树摘要。

输出：

- framework tags。
- package manager。
- confidence。
- evidence。

Phase 1 最小实现：

- 通过 `package.json` 依赖识别 Vue、Vite、TypeScript、Pinia、Vue Router、Axios、Element Plus。
- 当缺少依赖证据时，允许用文件树中的 `.vue`、`.ts`、`vite.config.*` 做低置信度补充识别。
- 通过 `packageManager` 字段或 lockfile 识别 npm、pnpm、yarn、bun。
- 通过 `pom.xml`、`build.gradle`、`settings.gradle` 和文件树识别 Java、Maven、Gradle、Spring Boot、Spring Web、Spring Security、MyBatis/JPA、JUnit。
- 当缺少依赖证据时，允许用 `src/main/java`、`src/main/resources`、`*Application.java` 做低置信度补充识别。

### find_entrypoints

用途：寻找入口文件。

Vue/Vite 优先检查：

- `src/main.ts`
- `src/main.js`
- `src/App.vue`
- `src/router/index.ts`
- `vite.config.ts`

Java/Spring Boot 优先检查：

- `src/main/java/**/*Application.java`
- `src/main/resources/application.yml`
- `src/main/resources/application.yaml`
- `src/main/resources/application.properties`
- `pom.xml`
- `build.gradle`

Phase 1 最小实现会返回已存在的候选入口文件及其类型，为后续 Repo Map Builder 使用。

### extract_symbols

用途：提取函数、类、组件、路由、store、Controller、Service、Repository 等符号。

第一版可以简化为正则和轻量解析，不做高精度全量 AST。

### build_repo_map

用途：根据扫描结果、配置、入口和 symbols 构建 Repo Map。

输出：

- Repo Map JSON。
- warnings。
- evidence。

### generate_doc

用途：生成项目说明书和项目解读报告。

输入：

- Repo Map。
- evidence。
- 用户问题或文档类型。
- 可选 `project_manual_context` 仅用于 legacy/兼容分析入口；报告后的右侧追问应使用 `/api/agent/ask`。

输出：

- project manual。
- project map。
- module summaries。
- key entrypoints。
- reading route。
- call chain candidates。
- 依据文件。
- 不确定点。

当前 MVP 实现：

- 由 `code_reader_agent.runtime.analysis.build_project_report` 为 `/api/agent/run` 生成 `report`。
- 由 `code_reader_agent.runtime.analysis.build_project_manual` 为 `/api/agent/run` 生成 `project_manual`；其中 `overview` 可使用 LLM 返回并通过校验的 `project_summary` 覆盖。
- 报告基于 Repo Map、只读工具调用、evidence、LLM/fallback 输出和 warnings。
- 即使 LLM 不可用，也必须返回结构化 `ProjectManual` 和 `ProjectReport`。
- 后续追问通过 `/api/agent/ask` 检索 Project Memory 和 Session Memory；缺少细节时仍通过只读工具补证据。

## 第二版工具规划

### trace_imports

追踪 import 依赖。

### trace_api_flow

追踪接口调用链。

Vue 项目优先从页面、store、API 模块、request 封装和 Axios/fetch 调用开始。

Java 项目优先从 Controller mapping、Service 调用、Repository/Mapper 调用和配置文件开始。

### git_status

只读查看 Git 状态。

### git_diff

只读查看文档或生成结果变更。

### run_command

运行命令，但必须用户确认。

## 工具调用记录

每次工具调用应记录：

- tool_name
- input summary
- output summary
- status
- started_at
- ended_at
- error
- reason
- evidence ids

`reason` 用于说明为什么调用该工具，例如“用户询问指定文件，需要读取真实代码片段”或“接口问题需要提取前端调用候选”。这些记录需要展示在 Evidence Panel 或 Ask Trace 中。

当前 MVP 中，`/api/agent/run` 会返回紧凑版 `tool_calls` 和 `trace_events`，用于前端展示 `scan_project`、`build_repo_map`、`read_file`、`search_code`、Planner 计划、Context Snapshot 和 Report Writer 输出。`/api/agent/ask` 会额外返回 `tool_plan`、`code_evidence` 和 `context_pack`，用于展示为什么调用只读工具以及哪些证据进入回答上下文。

## Phase 5.0：LLM 可调用工具白名单

最小 LLM Agent Loop 只允许模型调用只读工具：

- `scan_project`
- `build_repo_map`
- `read_file`
- `search_code`

这些工具由后端执行，LLM 只提出 tool call 请求。工具结果会回填给 LLM，并同时记录到 `tool_calls` 和 `agent_steps`。

上下文预算熔断：

- 默认 `max_context_chars=24000`，按工具结果 JSON 字符数近似控制 token 消耗。
- 默认 `max_tool_calls=8`。
- 默认 `max_read_files=4`。
- 任一预算超限时，不再把完整工具结果追加给 LLM，返回 deterministic fallback，并在 warnings、agent steps 和 trace events 中记录 `context budget exceeded`。

仍然禁止：

- `run_command`
- 写文件或编辑代码。
- Git 操作。
- 删除文件。
- 读取敏感文件。

如果 LLM 请求不在白名单内的工具，后端必须返回 tool error，并把该请求记录为 warning。
