# Repo Map Schema

## 设计目标

Repo Map 是 CodeReader Agent 的核心结构化项目地图。它需要同时服务于：

- 前端可视化展示。
- Context Manager 选择上下文。
- Agent 回答问题。
- Report Writer 生成项目地图、模块说明、关键入口、阅读路线和调用链候选报告。
- Reviewer 检查回答是否有证据。
- 后续复用扫描结果。

Repo Map 不能只保存模型总结，还要保存确定性扫描结果和 evidence。

## 顶层字段

```text
repo_map:
- project_name
- project_path
- project_summary
- detected_stack
- stack_explanations
- directory_insights
- reading_recommendations
- package_manager
- run_scripts
- entrypoints
- modules
- files
- dependencies
- routes
- api_endpoints
- api_flows
- auth_flows
- stores
- java_packages
- controllers
- services
- repositories
- components
- evidence
- generated_at
```

## Project Summary 结构

```text
project_summary:
- one_liner
- audience
- problem
- confidence
- evidence
```

字段说明：

- `one_liner`：一句话解释项目看起来是做什么的。
- `audience`：面向谁，证据不足时必须保守说明。
- `problem`：解决什么问题，不能脱离 README、配置、入口或目录证据。
- `confidence`：总览判断置信度。
- `evidence`：支撑总览的文件路径。

## Stack Explanation 结构

```text
stack_explanation:
- name
- category
- purpose
- evidence_source
- confidence
```

`detected_stack` 只保存识别标签；`stack_explanations` 面向用户解释该技术在项目中的作用，例如 FastAPI 提供后端接口、Vite 负责前端构建、Pinia 负责状态管理。

## Directory Insight 与 Reading Recommendation

```text
directory_insight:
- path
- role
- importance: core | supporting | skippable
- reason

reading_recommendation:
- path
- action: read_first | skip_for_now
- reason
- priority
```

目录理解用于告诉用户哪些目录是核心，哪些目录可以先跳过。阅读建议用于第一屏给出优先阅读路径，不代表完整调用链。

## Project Manual 结构

`ProjectManual` 不是新的扫描来源。它作为 `/api/agent/run` 的 `project_manual` 返回；报告后的追问优先使用由它和 Repo Map 派生出的 `ProjectMemory`。除 `overview` 外，第一版说明书主体仍由 Repo Map 确定性组装；`overview` 可由 LLM 基于 README 和只读工具上下文生成并覆盖 Repo Map 的确定性基线。

```text
project_manual:
- title
- overview
- technology_stack
- modules
- entrypoints
- directory_tree
- key_directories
- evidence
- uncertainties
- generated_by
```

字段说明：

- `overview`：复用 `ProjectSummary`，回答“这是一个什么项目”。优先使用 LLM 校验后的 `project_summary`；LLM 不可用、输出不合法或触发预算熔断时，回退到 `repo_map.project_summary`。
- `technology_stack`：复用 `StackExplanation`，解释技术栈和项目作用。
- `modules`：模块作用说明，来自 Repo Map modules。
- `entrypoints`：入口候选及解释，来自扫描器 entrypoints。
- `directory_tree`：真实扫描到的文件树截断视图。
- `key_directories`：关键目录解释，来自 `directory_insights`。
- `evidence`：支撑说明书的文件片段或配置证据。
- `uncertainties`：证据不足、未运行项目、调用链候选级等限制说明。

## Project Memory 结构

`ProjectMemory` 是报告生成后的 Ask 模式检索层。它不是新的扫描来源，而是从 Repo Map、Project Manual 和只读解析工具派生出来的结构化记忆。

```text
project_memory:
- project_id
- project_name
- project_path
- project_memory
- module_summaries
- file_summaries
- api_index
- symbol_index
- flow_index
- updated_at
```

### Project Memory Overview

```text
project_memory:
- positioning
- description
- project_type
- tech_stack
- startup_commands
- entry_points
- build_tools
- config_files
- external_dependencies
- modules
- directory_summary
```

### Module Summary

```text
module_summary:
- name
- responsibility
- role
- entry_files
- controller_files
- service_files
- view_files
- api_files
- related_files
- related_apis
- related_entities
```

### File Summary

```text
file_summary:
- path
- responsibility
- role
- language
- symbols
- imports
- exports
- related_apis
- hash
```

### API Index

```text
api_index:
- path
- method
- backend_method
- backend_file
- frontend_call_file
- frontend_calls
- request_type
- response_type
- description
```

### Symbol Index

```text
symbol_index:
- name
- kind
- file_path
- signature
- summary
```

### Flow Index

```text
flow_index:
- name
- kind
- description
- steps
- evidence_files
- confidence
```

第一版 `api_index`、`symbol_index` 和 `flow_index` 是候选级索引：Spring Controller、前端 axios/fetch/request 调用、文件名/符号名、登录/auth/API 相关文件会被收集，但不声明精准 AST 级跨文件调用链。

## Module 结构

```text
module:
- id
- name
- type
- description
- responsibility
- key_files
- entry_files
- dependencies
- dependents
- reading_priority
- confidence
- evidence
```

字段说明：

- `id`：稳定模块标识。
- `name`：模块名称。
- `type`：例如 app、router、store、api、views、components、utils、config、controller、service、repository、domain、test。
- `description`：模块说明。
- `responsibility`：模块职责。
- `key_files`：关键文件路径。
- `entry_files`：入口文件路径。
- `dependencies`：依赖的模块 id。
- `dependents`：依赖该模块的模块 id。
- `reading_priority`：初次阅读优先级，数值越小越建议先读。
- `confidence`：结论置信度。
- `evidence`：支撑该模块判断的文件和片段。

## File 结构

```text
file:
- path
- role
- language
- framework
- importance_score
- summary
- symbols
- related_modules
- evidence
```

字段说明：

- `path`：项目内相对路径。
- `role`：入口、路由、页面、store、api、组件、配置、工具等。
- `language`：TypeScript、JavaScript、Vue、JSON、Java、XML、YAML、Properties、Gradle 等。
- `framework`：Vue、Vite、Pinia、Vue Router、Spring Boot、Spring MVC、Spring Security、MyBatis、JPA 等。
- `importance_score`：阅读优先级评分。
- `summary`：文件作用摘要。
- `symbols`：函数、类、组件、路由、store 等符号。
- `related_modules`：关联模块 id。
- `evidence`：读取证据。

## Evidence 结构

```text
evidence:
- id
- source
- path
- start_line
- end_line
- excerpt
- reason
- collected_by_tool
- collected_at
```

Evidence 只记录真实读取过的文件、配置或命令输出。Agent 回答不能把未读取内容伪装成 evidence。

Phase 4.5 兼容规则：

- `start_line`、`end_line`、`excerpt`、`collected_at` 是可选字段。
- 当系统只扫描到文件路径或文件树线索时，可以返回路径级 evidence，但不能伪造片段。
- 当 `read_file` 成功读取配置或源码时，应尽量返回 1-40 行内的片段摘录。
- 敏感文件、读取失败或超出安全边界时，返回 warning 或路径级 evidence，不让整个扫描崩溃。

## Repo Map 如何生成

1. `list_files` 扫描文件树。
2. `read_config` 读取配置文件。
3. `detect_framework` 根据依赖和文件结构识别技术栈。
4. `find_entrypoints` 寻找入口文件。
5. `extract_symbols` 简化提取路由、组件、store、API、Controller、Service、Repository 等符号。
6. `build_repo_map` 汇总模块、文件和 evidence。
7. Reviewer 检查是否存在无证据结论。

当前实现中，Repo Map Builder 会为 `package.json`、Java 构建文件和入口文件附带片段级 evidence；模块本身通过 evidence id 关联这些证据。

总览页增强后，Builder 还会读取 `README.md`（如存在）生成保守的一句话解释，并基于依赖、配置、入口和目录结构生成技术栈作用说明、目录理解和阅读建议。缺少 README 时，不会伪造业务用途，只返回低置信度概述。

## Repo Map 如何更新

第一版采用重新扫描生成。后续可以根据文件修改时间增量更新。

更新时需要：

- 保留项目路径和历史任务记录。
- 重新读取关键配置。
- 对发生变化的文件重新提取信息。
- 标记过期 evidence。

## Repo Map 如何给前端展示

前端使用 Repo Map 展示：

- 一句话项目解释。
- 技术栈作用说明。
- 目录理解和阅读建议。
- 技术栈标签。
- 文件树。
- 模块树。
- 入口文件列表。
- 重要文件列表。
- 接口调用链。
- 登录认证流程。
- 状态管理逻辑。
- 模块详情。
- 证据片段。
- 后续模块关系图和调用链图。

## Repo Map 如何给 Context Manager 使用

Context Manager 根据用户问题和当前 skill 从 Repo Map 选择：

- 相关模块。
- 关键文件。
- 入口文件。
- evidence。
- 需要进一步搜索的关键词。

## 如何避免模型幻觉

- 区分确定性扫描结果和模型推断。
- 每个关键结论尽量绑定 evidence。
- 回答中暴露依据文件路径。
- 缺少证据时标记为不确定。
- Reviewer Agent 检查过度猜测。
- 不把整个代码库一次性塞给模型。
