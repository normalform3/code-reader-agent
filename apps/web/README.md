# CodeReader Agent Web

这是 CodeReader Agent 的 Vite + React + TypeScript 本地 Web 工作台。

当前实现覆盖 MVP 工作台闭环：输入公开 GitHub 仓库链接，调用本地 API 导入只读缓存并生成 Repo Map，再展示 Planner 计划、Skill Registry、Context Snapshot、结构化项目解读报告、Trace Logger、模块、入口和证据。本地项目路径只作为内部扫描契约和开发调试能力保留。

## 计划职责

- 提供本地 Web UI。
- 输入公开 GitHub 仓库链接。
- 展示扫描进度。
- 展示文件树、模块树、技术栈和项目概览。
- 展示分析目标、Planner 计划、Skill Registry、Context Snapshot、Report 和 Trace Logger。
- 展示工具调用、已读取文件和 evidence。

## 本地运行

```bash
cd apps/web
npm install
npm run dev
```

默认调用 `http://127.0.0.1:8000` 的 FastAPI 服务。需要覆盖时可设置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## 计划技术栈

- React
- Vite
- TypeScript
- Tailwind CSS
- shadcn/ui
- React Flow
- Markdown Renderer
- Monaco Editor（后续）

## MVP 布局

- 左侧 Project Explorer。
- 中间 Codebase Map。
- 右侧 Agent Panel：分析目标、Planner、Skill Registry、Context Snapshot、Report、Trace。
- 底部 Execution / Evidence Panel。
