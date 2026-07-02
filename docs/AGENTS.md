# 多 Agent 协作设计

## 设计目标

多 Agent 协作不是为了增加复杂度，而是为了让代码理解任务有清晰分工、可展示过程和可验证结果。

第一版可以先用单进程编排模拟多个角色，不需要真正并发或多进程 Agent。

## Planner Agent

职责：

- 理解用户问题。
- 判断任务类型。
- 选择 skill。
- 生成分析计划。
- 设定完成条件。

可用 tools：

- 不直接读取大量文件。
- 可以读取 Repo Map 摘要。

输出：

- selected_skill
- task_goal
- search_plan
- expected_output

## Explorer Agent

职责：

- 根据 skill 搜索代码。
- 读取关键文件。
- 收集 evidence。
- 记录工具调用。

可用 tools：

- `list_files`
- `read_file`
- `search_code`
- `read_config`
- `detect_framework`
- `find_entrypoints`

输出：

- candidate_files
- evidence
- warnings
- missing_information

## Analyzer Agent

职责：

- 分析代码结构。
- 识别模块关系。
- 分析调用链和数据流。
- 将证据组织成解释结构。

可用 tools：

- `extract_symbols`
- `build_repo_map`
- 后续 `trace_imports`
- 后续 `trace_api_flow`

输出：

- findings
- relationships
- confidence
- uncertainty

## Writer Agent

职责：

- 生成面向用户的结构化回答。
- 生成 onboarding 总结。
- 输出推荐阅读路径。
- 保留证据引用。

输出：

- answer
- cited_files
- next_questions
- onboarding_doc

## Reviewer Agent

职责：

- 检查回答是否有依据。
- 检查是否遗漏关键文件。
- 检查是否过度猜测。
- 标记不确定点。

输出：

- review_status
- unsupported_claims
- missing_evidence
- revised_warnings

## Agent 间数据结构

```text
agent_task:
- task_id
- user_question
- selected_skill
- repo_map_id
- plan
- tool_calls
- evidence
- findings
- answer
- review
- status
```

## 示例流程：登录流程分析

用户问：“登录流程是怎么实现的？”

Planner Agent：

- 识别为 `auth_flow_skill`。

Explorer Agent：

- 搜索 `login`、`token`、`auth`、`beforeEach`、`interceptor`、`Authorization` 等关键词。
- 读取登录页面、用户 store、API 文件、request 封装和 router 文件。

Analyzer Agent：

- 分析登录提交、token 保存、路由守卫和请求拦截逻辑。

Writer Agent：

- 生成登录流程说明、调用链、关键文件列表和不确定点。

Reviewer Agent：

- 检查回答是否引用证据文件。
- 标记没有读取到的链路缺口。

UI：

- 展示当前 skill、已读取文件、工具调用记录、回答依据和警告。

## UI 展示要求

每次任务需要展示：

- 当前 Agent 步骤。
- 当前使用 skill。
- 工具调用记录。
- 已读取文件。
- evidence。
- Reviewer 警告。

## Phase 4：单 Agent 项目解读

Phase 4 先不实现完整多 Agent 编排，而是提供一个可验证的单 Agent 解读闭环。

职责：

- 接收用户问题和扫描结果。
- 固定选择 `project_overview_skill`。
- 基于 package 信息、技术栈标签、入口文件和 warnings 构造上下文。
- 生成版本化 prompt messages，供后续 LLM provider 使用。
- 在没有 LLM 的情况下返回确定性 onboarding 草稿。

输入：

- `project_path`
- `question`
- `ProjectScanResult`

输出：

- `skill`
- `prompt_version`
- `prompt_messages`
- `overview`
- `setup_summary`
- `reading_path`
- `evidence`
- `warnings`

边界：

- 不额外读取源码全文。
- 不调用外部 LLM。
- 不执行项目命令。
- 不伪造 Repo Map 或 evidence。
- 缺少 README、package scripts 或入口文件时必须返回 warning。

## Phase 4.5：最小 Skill Router + 可信 Evidence

Phase 4.5 仍不实现完整多 Agent 编排，但单 Agent 解读不再固定使用 `project_overview_skill`。

职责：

- 根据用户问题确定性选择 `project_overview_skill`、`setup_analysis_skill` 或 `frontend_analysis_skill`。
- 通过只读工具读取配置、入口和前端结构候选文件。
- 对登录/API 类问题只搜索候选关键词，不生成完整链路结论。
- 返回工具调用、已读取文件、片段 evidence、warnings 和推荐追问。

输出新增：

- `tool_calls`
- `read_files`
- `suggested_questions`
- evidence 的 `start_line`、`end_line`、`excerpt`

边界：

- 不调用外部 LLM。
- 不执行被分析项目命令。
- 不读取 `.env`、私钥、证书等敏感文件。
- 不把候选搜索结果说成完整认证或 API 调用链。
