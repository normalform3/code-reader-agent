# CodeReader Agent Web

这是 CodeReader Agent 的 Vite + React + TypeScript 本地 Web 工作台。

当前实现覆盖 Phase 3/4 的最小闭环：输入本地项目路径，调用本地 API 生成 Repo Map，展示模块、入口、证据和项目解读。

## 计划职责

- 提供本地 Web UI。
- 输入或选择项目路径。
- 展示扫描进度。
- 展示文件树、模块树、技术栈和项目概览。
- 展示 Agent 对话。
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
- 右侧 Agent Panel。
- 底部 Execution / Evidence Panel。
