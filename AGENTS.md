# CodeReader Agent 开发规则

## 项目目标

CodeReader Agent 是面向陌生 Java Web / 前后端项目的代码库理解 Agent。它的核心价值不是替代开发者写代码，也不是做普通代码问答，而是在用户给出目标后主动制定分析计划、调用只读工具、组织上下文，并生成可导航、可追踪、可复用的项目解读报告。

第一阶段重点：

- 输入公开 GitHub 仓库链接并创建分析任务。
- Planner 生成分析计划。
- Tool Executor 调用只读工具扫描项目并构建 Repo Map。
- Context Manager 管理项目上下文、任务上下文、符号上下文和当前记忆上下文。
- Skill Registry 根据技术栈选择 `SpringBootSkill`、`VueSkill` 或通用理解 skill。
- Analyzer 和 Report Writer 输出项目地图、模块说明、关键入口、阅读路线和调用链候选报告。
- Trace Logger 展示计划、工具调用、上下文更新和最终产物。

## 当前开发阶段

当前已具备可运行 MVP 雏形：GitHub 导入、只读扫描、Repo Map、确定性解释、最小 LLM tool loop、结构化报告字段和 React/Vite 工作台。

允许做：

- 围绕“目标驱动的代码库理解报告”做小步增量。
- 强化公开 GitHub 项目导入、Repo Map、分析计划、上下文快照、报告和 trace 展示。
- 补充 Vue/Vite 与 Java/Spring Boot 的确定性识别、只读工具和证据。
- 更新与行为变更对应的文档和测试。

不要做：

- 自动修改代码。
- 写文件工具、运行被分析项目命令或 Git 操作。
- 企业级任务队列、云端多用户系统或桌面端打包。
- 精准全量 AST 图谱和完整跨文件调用链追踪。
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

- Planner 负责把用户目标转成分析计划。
- Tool Executor 负责执行只读工具并记录调用结果。
- Context Manager 负责组织项目、任务、符号和当前记忆上下文。
- Skill Registry 负责按技术栈选择 `SpringBootSkill`、`VueSkill` 或通用理解 skill。
- Analyzer 负责基于 Repo Map、工具结果和上下文生成理解结果。
- Report Writer 负责生成结构化项目解读报告。
- Trace Logger 负责记录计划、工具调用、上下文更新和最终产物。
- Reviewer 仍属于后续增强，负责检查证据、遗漏和过度猜测。

不要增加没有清晰责任、终止条件和评价标准的 Agent。

## MVP 纪律

第一版主要支持公开 GitHub 上的 Java Web / Spring Boot 与 Vue/Vite 前后端项目。新增能力必须服务于：

- 项目导入和分析任务创建。
- Repo Map、模块说明、关键入口和阅读路线。
- 技术栈 Skill 选择。
- 上下文组织和证据追踪。
- 结构化项目解读报告和 trace 展示。

React、Next.js、FastAPI、Express、多语言项目支持可以作为 best-effort 识别保留，但不作为第一版核心承诺。

## 验证要求

每次修改后尽量运行最小相关检查，并诚实报告结果。当前阶段建议：

```bash
python -m compileall src
python -m pytest
```

如果测试不存在或依赖未安装，需要明确说明。
