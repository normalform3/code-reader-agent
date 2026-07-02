# CodeReader Agent 开发规则

## 项目目标

CodeReader Agent 是面向陌生代码库的本地可视化理解型 Coding Agent。它的核心价值是帮助开发者快速理解一个项目，而不是优先替用户自动写代码。

第一阶段重点：

- 扫描项目。
- 生成 Repo Map。
- 展示模块、文件、入口和证据。
- 支持基于代码证据的 Agent 解释。
- 提供接近桌面端 Coding Agent 的本地 Web UI。

## 当前开发阶段

当前处于 Phase 0：项目规划与脚手架阶段。

允许做：

- 创建和维护文档。
- 创建轻量目录结构。
- 添加少量占位代码。
- 明确 MVP 边界、架构、工具、skills、上下文和 Agent 协作方案。

不要做：

- 完整 Agent Loop。
- LLM 接入。
- 复杂前端页面。
- 图谱引擎。
- 自动修改代码。
- 桌面端打包。

## 产品定位规则

- 不要把项目退化成普通代码问答工具。
- 不要只做 CLI；CLI 只能作为调试入口。
- 不要一开始追求完整桌面端打包。
- 不要把重点放在自动写代码上。
- 不要让模型一次性读取整个代码库。
- 不要为了展示技术而加入无关复杂功能。

## 代码风格

- 保持小步、清晰、可验证。
- 优先显式数据流，不隐藏错误。
- deterministic 逻辑优先使用普通代码实现。
- LLM 只用于理解、总结、分类、模糊推理和结构化解释。
- 不新增生产依赖，除非有明确必要并记录到 `docs/DECISIONS.md`。

## 文档维护要求

修改行为和对应文档：

- 修改架构：同步更新 `docs/ARCHITECTURE.md`。
- 修改 UI 设计：同步更新 `docs/UI_DESIGN.md`。
- 修改 Repo Map 数据结构：同步更新 `docs/REPO_MAP_SCHEMA.md`。
- 新增或修改工具：同步更新 `docs/TOOLS.md`。
- 新增或修改 skill：同步更新 `docs/SKILLS.md`。
- 修改 Agent 流程：同步更新 `docs/AGENTS.md`。
- 改变阶段计划：同步更新 `docs/ROADMAP.md` 和 `docs/PROJECT_PLAN.md`。
- 重要设计变更：新增或更新 `docs/DECISIONS.md`。

## 工具和安全边界

- Phase 1 工具默认只读。
- 任何写文件、运行命令、修改代码、Git 操作都必须先获得用户确认。
- 不读取或暴露密钥、token、私有 endpoint、workspace id、bucket path、signed URL。
- 回答必须尽量绑定证据文件；不确定时明确说明不确定。

## Agent 设计规则

- Planner Agent 负责理解任务并选择 skill。
- Explorer Agent 负责搜索、读取文件、收集证据。
- Analyzer Agent 负责分析结构、模块关系和流程。
- Writer Agent 负责生成结构化解释或文档。
- Reviewer Agent 负责检查证据、遗漏和过度猜测。

不要增加没有清晰责任、终止条件和评价标准的 Agent。

## MVP 纪律

第一版只支持 Vue3 / Vite / TypeScript 项目的基础理解闭环。新增能力必须服务于：

- 扫描项目。
- 构建 Repo Map。
- 模块可视化。
- Agent 解释。
- 证据追踪。

React、Next.js、FastAPI、Spring Boot、Express、多语言项目支持属于后续阶段。

## 验证要求

每次修改后尽量运行最小相关检查，并诚实报告结果。当前阶段建议：

```bash
python -m compileall src
python -m pytest
```

如果测试不存在或依赖未安装，需要明确说明。
