# CodeReader Agent API

这是 FastAPI 本地服务的位置。

当前已提供 Phase 1-4 的最小本地 API：只读项目扫描、Repo Map 生成和确定性项目解读。

## 计划职责

- 校验本地项目路径。
- 启动项目扫描任务。
- 调用 Agent Runtime。
- 返回 Repo Map。
- 向前端推送任务事件和工具调用记录。

## 当前接口

- `POST /api/projects/scan`：已实现，接收本地项目路径，返回文件树摘要、package 信息、技术栈标签、入口文件和 warnings。
- `POST /api/projects/import-github`：已实现，接收公开 GitHub 仓库链接，导入到本地只读缓存，返回可继续扫描的 `project_path`。
- `POST /api/projects/repo-map`：已实现，接收本地项目路径，返回基础 Repo Map、模块、文件角色、入口、证据和 warnings。
- `POST /api/agent/project-interpretation`：已实现，接收本地项目路径和问题，返回项目总览、启动建议、推荐阅读路径、prompt payload、证据和 warnings。

## 后续计划接口

- `POST /api/agent/questions`
- `GET /api/tasks/{task_id}/events`

## 安全边界

- 默认只读扫描。
- 不读取敏感环境文件。
- 不运行项目命令，除非用户确认。
- 不修改用户项目文件。
