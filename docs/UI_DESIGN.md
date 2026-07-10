# UI 设计

## 设计目标

CodeReader Agent 的界面应接近桌面端 Coding Agent 的工作台体验，而不是普通文档页或聊天页。用户进入产品后应首先看到代码库总览，再进入项目结构、模块地图和 Agent 对话。

MVP 的右侧 Agent 区域不是普通聊天框，而是“分析目标 / Agent 执行”面板：展示 Planner 计划、Skill Registry、Context Snapshot、项目说明书、结构化项目解读报告和 Trace Logger。

## 主界面布局

主界面改为会话式工作台，左侧固定为项目会话边栏，右侧固定为 Ask 边栏，只有中间 Codebase Map 主页面独立上下滚动。

主界面分为三个区域：

- 左侧：Project Sessions Sidebar
- 中间：Codebase Map
- 右侧：Agent Panel

工具、Skill 和模型设置入口位于左侧底部，以内置弹窗打开，不切换主页面：

- 工具管理
- Skill 管理
- 模型设置

## 左侧：Project Sessions Sidebar

展示内容：

- GitHub 仓库链接输入入口，用于新建项目分析会话。
- 历史项目列表，每个项目像一条 ChatGPT 会话。
- 项目名、GitHub repository、当前状态和最后更新时间。
- 左下角固定工具管理、Skill 管理和模型设置入口。
- 当前项目会话选中态。

交互：

- 输入公开 GitHub 仓库链接后，系统先导入只读仓库快照，再自动生成 Repo Map，并创建或更新本地项目会话。
- 点击历史项目时，根据保存的 `project_path` 重新加载 Repo Map 和 Agent 结果。
- 左侧边栏支持收起和展开，收起后只保留窄工具栏，不影响中间工作台阅读空间。
- 左侧边栏支持在 `历史项目` 与 `当前项目文件` 两个视图之间切换。
- 选中历史项目或完成新项目导入后，左侧可切换到当前项目文件树，快速浏览真实目录结构。
- 当前项目文件树支持目录展开/收起，文件作为叶子节点展示。
- 删除历史项目只移除侧边栏会话记录，不删除 `.codereader/repos` 下的仓库缓存。
- 左侧边栏固定宽度和视口高度，历史项目列表在边栏内部滚动。
- 根据扫描状态显示 loading、empty、error、success 状态。
- 模型设置弹窗只配置百炼模型名称，显示 `litellm` / `langgraph` 状态和百炼环境变量配置状态，并提供连通性测试。

## 项目工作台

展示内容：

- GitHub 导入状态和缓存复用提示。
- 项目文件树。
- 技术栈及其在项目中的作用。
- 入口文件列表。
- 重要文件列表。
- 文件角色、语言和框架摘要。

- 点击文件查看文件角色摘要。

## 中间：Codebase Map

展示内容：

- 中间主页面整体称为“项目说明书”。
- 项目 Header：展示项目名、GitHub 链接和当前分析状态。
- GitHub 链接下方展示首次项目说明书生成流程，使用 `/api/agent/run/stream` 流式追加公开 Agent 步骤，并支持折叠。
- 代码库总览卡片：项目概述、项目是什么、主要做什么、技术栈、构建工具、入口候选和置信度。
- 项目说明书卡片：只保留关键目录 / Repo Map 导航。
- 目录理解：只展示关键目录导航，不展示完整文件树；目录解释用于帮助用户决定从哪里开始读。
- Planner 计划。
- Skill Registry 选择结果。
- Context Snapshot。
- 项目说明书和结构化项目解读报告。
- Trace Logger 执行轨迹。
- 后续阶段展示调用链图、页面到 API 的数据流、登录认证流程图。

MVP 中间主页面不再展示“核心模块”以下的模块卡片、当前模块详情或模块 evidence；这些结构仍可保留在 API 数据中，后续按需放入单独视图或 Ask 证据抽屉。

## 右侧：Agent Panel

展示内容：

- 类似 Copilot Ask 的侧边栏对话流。
- 顶部提供 Ask conversation 切换和“新对话”按钮；同一个项目可以打开多个彼此隔离的 Ask 会话。
- 右下角固定用户提问输入框。
- 右侧边栏固定在视口内，顶部 header 和底部输入框固定，中间对话与上下文内容可上下滚动。
- 右侧边栏和中间主页面之间提供折叠按钮；折叠后隐藏中间 Codebase Map，Ask 占满左侧项目栏之外的剩余空间。
- Ask 消息内容宽度跟随边栏，不出现左右滑动；长路径、代码片段和 trace 摘要必须自动换行或截断。
- Agent 回答和用户追问历史。
- 当前使用的 skill。
- 当前读取的文件。
- 回答依据。
- warnings 和不确定点。
- 用户提问后，Ask 边栏通过 SSE 显示公开 Agent 进度，包括节点完成、工具计划、工具结果、Context Pack 和回答生成状态。
- 切换 Ask conversation 只切换右侧消息和 Session Memory，不切换中间项目说明书；每轮回答仍通过只读工具读取当前工作区真实代码。
- 右侧 Ask 不再展示阅读路径折叠块；阅读路径留在中间项目说明书主区。

MVP 不在 Ask 边栏内展示固定问题或推荐问题；导入分析使用的默认项目说明书问题只作为内部任务输入。

## Execution / Evidence 展示

当前 MVP 暂不展示底部横栏，避免遮挡中间工作台。API 返回的 `tool_calls`、Repo Map evidence、Agent evidence 和 warnings 暂时保留在数据结构中，后续可放入右侧 Ask 折叠详情或单独抽屉。

## 工具 / Skill 管理弹窗

工具管理和 Skill 管理都通过本地 registry API 读取和保存到 `.codereader/state.json`，或 `CODEREADER_STATE_DIR/state.json`。

展示内容：

- 当前内置和自定义 tools / skills。
- 列表默认只展示名称、描述、启用状态和 `内置` / `自定义` 标记。
- 点击列表项后展示结构化详情，例如输入、输出、安全规则、触发条件、优先读取文件和可用 tools。
- 启用状态。

交互：

- 支持搜索、启用/禁用、编辑说明、编辑结构化详情、新增自定义项。
- 内置项不能被真正删除，删除动作会将其禁用。
- 自定义项可以删除。
- 第一版管理弹窗只管理 registry 展示和本地配置；自定义 skill 是否参与 Agent 路由留到后续实现。
- 打开或关闭管理弹窗不会重载当前 Repo Map 或 Agent 报告。

## 主要页面状态

- Empty：尚未选择项目。
- Scanning：正在扫描文件树和配置。
- Ready：Repo Map 已生成，可以查看报告和继续分析。
- Analyzing：Agent 正在执行分析任务。
- Error：项目路径无效、读取失败或解析失败。
- Partial：部分文件读取失败，但系统仍展示可用结果和警告。

## 用户操作流程

1. 输入公开 GitHub 仓库链接。
2. 点击 Analyze。
3. 在中间项目说明书 Header 下方查看导入和分析进度。
4. 首次项目说明书生成优先使用 `/api/agent/run/stream` 接收 SSE 进度；等待期间在中间主页面展示扫描、Repo Map、Planner、Project Manual 和 Report Writer 节点。
5. 查看代码库总览和关键目录 / Repo Map 导航。
6. 在右侧 Ask 边栏输入追问；前端调用 `/api/agent/ask`，由后端基于 Project Memory、Session Memory 和只读工具生成证据化回答。
7. 后续 Ask 优先使用 `/api/agent/ask/stream` 接收 SSE 进度；等待期间直接在聊天气泡中显示 Agent trace，完成后展示最终回答、相关文件和上下文信息。

## MVP UI 范围

MVP 必须包括：

- GitHub 仓库链接分析入口。
- 扫描进度展示。
- 历史项目侧边栏。
- 一句话项目解释。
- 项目说明书卡片。
- 技术栈识别结果和作用说明。
- 顶层/分层目录解读。
- 文件树。
- 项目概览卡片。
- 分析目标输入框。
- Planner 计划展示。
- Skill Registry 选择结果。
- Context Snapshot 展示。
- 结构化项目解读报告展示。
- Trace Logger 展示。
- 工具管理和 Skill 管理弹窗。

## 后续高级 UI 能力

- React Flow 模块关系图。
- 调用链图。
- 登录流程图。
- 页面数据流图。
- Monaco 代码片段预览。
- 任务历史。
- 多项目切换。
- 桌面端打包适配。
