# Tool System

## 设计原则

第一版工具默认只读。CodeReader Agent 的核心任务是理解代码库，不是修改代码库。

任何写文件、运行命令、修改代码、Git 操作或删除文件的行为都必须先请求用户确认。

## 第一版工具

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

用途：生成项目导读文档。

输入：

- Repo Map。
- evidence。
- 用户问题或文档类型。

输出：

- onboarding summary。
- 依据文件。
- 不确定点。

Phase 4 最小实现：

- 由 `code_reader_agent.interpreter.interpret_project` 提供单 Agent 解读结果。
- 不调用真实 LLM，只生成版本化 prompt payload 和确定性 fallback 文本。
- evidence 只来自扫描到的 `package.json`、文件树技术栈证据和入口文件。
- 缺少启动脚本、package 信息或入口文件时通过 warnings 暴露。

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
- evidence ids

这些记录需要展示在 Evidence Panel 中。

Phase 4.5 中，Agent 解释 API 会返回紧凑版 `tool_calls`，用于前端展示 `list_files`、`detect_framework`、`read_file`、`search_code` 和解释器步骤。

## Phase 5.0：LLM 可调用工具白名单

最小 LLM Agent Loop 只允许模型调用只读工具：

- `scan_project`
- `build_repo_map`
- `read_file`
- `search_code`

这些工具由后端执行，LLM 只提出 tool call 请求。工具结果会回填给 LLM，并同时记录到 `tool_calls` 和 `agent_steps`。

仍然禁止：

- `run_command`
- 写文件或编辑代码。
- Git 操作。
- 删除文件。
- 读取敏感文件。

如果 LLM 请求不在白名单内的工具，后端必须返回 tool error，并把该请求记录为 warning。
