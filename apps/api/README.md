# CodeReader Agent API

这是 FastAPI 本地服务的位置。

当前已提供 MVP 本地 API：公开 GitHub 仓库导入、只读项目扫描、Repo Map 生成、确定性项目解读、最小只读 LLM tool loop，以及目标驱动分析任务结果。

## 计划职责

- 校验公开 GitHub 链接；本地项目路径只作为内部扫描契约和开发调试能力保留。
- 启动项目扫描任务。
- 调用 Agent Runtime。
- 返回 Repo Map。
- 返回 Planner 计划、Skill Registry、Context Snapshot、Report、Trace Logger 和工具调用记录。

## 当前接口

- `POST /api/projects/scan`：已实现，接收本地项目路径，返回文件树摘要、package 信息、技术栈标签、入口文件和 warnings。
- `POST /api/projects/import-github`：已实现，接收公开 GitHub 仓库链接，导入到本地只读缓存，返回可继续扫描的 `project_path`。
- `POST /api/projects/repo-map`：已实现，接收本地项目路径，返回基础 Repo Map、模块、文件角色、入口、证据和 warnings。
- `POST /api/agent/project-interpretation`：已实现，接收本地项目路径和问题，返回项目总览、启动建议、推荐阅读路径、prompt payload、证据和 warnings。
- `POST /api/agent/run`：首次项目理解报告入口，接收内部项目路径和分析目标，返回兼容旧字段以及 `task_id`、`analysis_goal`、`analysis_plan`、`selected_skills`、`context_snapshot`、`project_memory`、`report` 和 `trace_events`。
- `POST /api/agent/run/stream`：首次项目说明书流式入口，使用 SSE 返回 `step`、`trace`、`final` 和 `error` 事件，`final.event` 是完整 `AgentRunResult`。
- `POST /api/agent/ask`：报告后的 Ask 模式入口，返回 intent、answer、related files、implementation path、references、tool calls、trace events 和 session memory。
- `POST /api/agent/ask/stream`：报告后的 Ask 流式入口，使用 SSE 返回公开执行轨迹和最终 Ask 结果。

## 后续计划接口

- `GET /api/tasks/{task_id}/events`
- Reviewer 或更细粒度事件流相关接口。

## 安全边界

- 默认只读扫描。
- 不读取敏感环境文件。
- 不运行项目命令，除非用户确认。
- 不修改用户项目文件。
