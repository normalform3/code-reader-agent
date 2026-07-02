# Repo Map Schema

## 设计目标

Repo Map 是 CodeReader Agent 的核心结构化项目地图。它需要同时服务于：

- 前端可视化展示。
- Context Manager 选择上下文。
- Agent 回答问题。
- Reviewer 检查回答是否有证据。
- 后续复用扫描结果。

Repo Map 不能只保存模型总结，还要保存确定性扫描结果和 evidence。

## 顶层字段

```text
repo_map:
- project_name
- project_path
- detected_stack
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

## Repo Map 如何生成

1. `list_files` 扫描文件树。
2. `read_config` 读取配置文件。
3. `detect_framework` 根据依赖和文件结构识别技术栈。
4. `find_entrypoints` 寻找入口文件。
5. `extract_symbols` 简化提取路由、组件、store、API、Controller、Service、Repository 等符号。
6. `build_repo_map` 汇总模块、文件和 evidence。
7. Reviewer 检查是否存在无证据结论。

## Repo Map 如何更新

第一版采用重新扫描生成。后续可以根据文件修改时间增量更新。

更新时需要：

- 保留项目路径和历史任务记录。
- 重新读取关键配置。
- 对发生变化的文件重新提取信息。
- 标记过期 evidence。

## Repo Map 如何给前端展示

前端使用 Repo Map 展示：

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
