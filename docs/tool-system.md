# Runtime Tool System

Tool 模块是 CodeReader Agent 的只读代码证据获取层。它不负责生成最终回答，也不负责决定技术栈分析策略；它只负责在 Ask 模式中安全、可观测地获取真实代码证据。

当前 Ask 模式是只读工具模式，不会修改用户代码，不运行被分析项目命令，不执行 Git 操作，也不会联网抓取额外代码。

## 组件职责

```text
Tool Planner
-> Tool Executor
-> Tool Registry
-> Tool Handler
-> Tool Result Processor
-> Tool Trace Store
-> Context Pack
```

- `Tool Registry`：注册运行时工具定义，包括名称、描述、category、permission、risk level、available modes、input schema、timeout 和 handler。
- `Tool Planner`：根据 intent、Skill hints、Code Knowledge Index 命中和 Session Memory 生成 `PlannedToolCall`。
- `Tool Executor`：执行工具调用，并校验工具是否存在、当前 mode 是否允许、permission/risk 是否安全、参数是否符合 schema、路径是否仍在项目根目录内、是否超时。
- `Tool Result Processor`：把工具原始结果裁剪成 `CodeEvidence`、`EvidenceRef`、文件列表和摘要，避免把完整文件直接塞进 Context Pack。
- `Tool Trace Store`：记录工具名、参数、调用原因、成功状态、耗时、时间戳和结果摘要。

## Ask 模式安全规则

Ask 模式只允许满足以下条件的工具：

- `permission = read`
- `risk_level = safe`
- `available_in_modes` 包含 `ask`

Ask 模式禁止：

- 写文件、编辑文件、删除文件。
- 任意 shell 命令。
- Git commit、push、reset 等操作。
- 运行被分析项目的 build/test/lint 命令。
- 网络抓取、数据库写入或任何会修改用户项目的操作。

## 当前工具清单

文件系统：

- `list_files`
- `read_file`
- `read_file_chunk`
- `get_file_metadata`

搜索：

- `search_keyword`
- `search_symbol`
- `search_api_path`
- `search_file_by_name`

解析：

- `parse_dependencies`
- `parse_package_scripts`
- `parse_controller`
- `parse_routes`
- `parse_api_calls`
- `parse_mapper`

索引查询：

- `query_project_memory`
- `query_code_index`
- `query_api_index`
- `query_flow_index`
- `query_symbol_index`

`query_*_index` 第一版只查询当前 `ProjectMemory` 和 Code Knowledge Index，不读取文件、不联网、不写状态。

## Tool 与 Skill 的关系

Skill 知道某个技术栈应该怎么分析，例如 Spring Boot Skill 会提示检查 Controller、SecurityConfig、JWT 过滤器和 application 配置。

Tool 执行具体只读动作，例如 `search_keyword("AuthController")`、`read_file("src/api/auth.ts")` 或 `parse_controller()`。

Skill 只能贡献 query hints、tool plan hints 和 answer prompts；它不能直接回答问题，也不能绕过 Tool Registry 直接读取文件。最终回答必须尽量基于 Project Memory、Code Knowledge Index 和 Tool Executor 产生的 Code Evidence。

## 扩展方向

后续可以为 Plan / Agent 模式增加 caution execute tools，例如 `run_tests`、`run_build` 或 `run_lint`，但需要用户确认和更严格的权限边界。Dangerous write tools 当前不实现。
