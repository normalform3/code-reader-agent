# Design: Lightweight Skill Router

CodeReader Agent 的 Skill Router 是现有 Skill Registry 之上的两层轻量路由系统。它的目标不是把系统扩展成复杂多 Agent 编排，而是在项目扫描和 Ask 追问两个关键阶段减少上下文噪声，让技术栈 Skill 只在相关场景参与。

## Skill 定义

Skill 是技术栈级代码理解插件，不是单纯提示词。一个 Skill 包含：

- Skill 名称。
- 激活条件。
- 扫描规则。
- 解析函数。
- 索引构建逻辑。
- Ask query hints。
- Ask tool plan hints。
- Answer prompt。

## 项目级路由

项目首次扫描阶段的流程：

```text
项目基础扫描
-> 构建 Repo Map
-> SkillRegistry 遍历内置 Skill
-> 每个 Skill 执行 detect(repo_map)
-> 根据 matched / confidence / reason 生成 ActiveSkill
-> 只有 ActiveSkill 执行 scan()
-> scan 结果写入 ProjectMemory 的 Code Knowledge Index
```

导入 Spring Boot + Vue 项目时，当前可以自动激活 `SpringBootSkill`、`JavaWebSkill`、`VueSkill`、`RestApiSkill`，如果存在 Mapper/XML/SQL/实体线索，也会激活 `MyBatisSkill`。激活结果包含 Skill 名称、置信度和原因。

## 问题级路由

Ask 模式中的流程：

```text
用户问题
-> Query Rewriter 指代消解
-> Intent Classifier 意图识别
-> SkillRouter 从 activeSkills 中选择本轮 routed skills
-> routed skills 提供 query hints / tool hints / answer prompts
-> Context Retriever 检索 Project Memory、Code Knowledge Index、Session Memory
-> Tool Planner 结合索引命中和 Skill hints 规划只读工具
-> Evidence Collector 读取真实代码
-> Context Builder 构造 Context Pack
-> Answer Composer 生成证据化回答
```

问题级路由只从 ActiveSkill 中选择本轮相关 Skill，判断依据包括问题意图、关键词、Code Knowledge Index 命中、resolved query 引用和 Session Memory 的关注文件/API/流程。

## 为什么只做轻量路由

当前阶段更需要稳定的项目理解闭环，而不是复杂编排系统。轻量路由有三个好处：

- 可解释：每个 routed skill 都有置信度、原因和 signals。
- 可测试：项目级 detect、scan、index merge 和 Ask routing 都可以用确定性测试覆盖。
- 低噪声：避免所有 Skill 每轮 Ask 都贡献 hints 和工具建议。

当前不做复杂多 Agent 路由，也不让 Skill 直接回答问题。Skill 只能影响检索、只读工具规划和回答组织；事实依据仍来自 ProjectMemory、Code Knowledge Index 和只读工具 evidence。

## 当前 Skill

- `JavaWebSkill`：Java Web 分层结构。
- `SpringBootSkill`：Spring Boot 启动类、配置、Controller 和安全配置。
- `MyBatisSkill`：Mapper、XML、SQL、实体和表关系候选。
- `VueSkill`：Vue 入口、路由、页面、组件、状态和 API 调用。
- `RestApiSkill`：后端接口、前端调用和 REST 映射候选。

后续可以扩展为工具级路由、跨 Skill 协作排序和更复杂的 Skill 编排，但需要先保持 read-only evidence 边界和可观测 trace。
