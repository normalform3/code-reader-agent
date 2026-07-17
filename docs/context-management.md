# Context Management

Context Manager 的职责是为项目理解和 Ask 模式选择必要上下文，避免把整个代码库一次性塞给模型。

## 上下文来源

Ask 模式主要使用四类上下文：

- Project Memory：项目定位、技术栈、入口、启动方式、配置、依赖和模块摘要。
- Code Knowledge Index：Module Summary、File Summary、API Index、Symbol Index、Flow Index、Route Index、Frontend API Call Index、Data Model Index、Mapper Relation 候选。
- Session Memory：当前话题、关注模块、关注文件/API/流程、最近 8 轮问答、持久历史摘要和已归档轮次数。
- Routed Skill Hints：本轮相关 Skill 提供的 query hints、tool plan hints 和 answer prompts。

## 与 Skill Router 的关系

项目级 Skill 路由决定哪些 Skill 能参与首次扫描和索引构建。只有 ActiveSkill 的扫描结果会写入 Code Knowledge Index。

问题级 Skill 路由决定 Ask 本轮使用哪些 Skill。Context Retriever 只使用 routed skills 的 query hints，LLM Tool Planner 将它们作为工具决策提示，Context Builder 只注入 routed skills 的 answer prompts。

## Ask 上下文选择流程

```text
Query Rewriter 处理指代
-> LLM Intent Classifier 识别问题类型
-> SkillRouter 选择本轮 routed skills
-> Context Retriever 检索 Project Memory / Code Knowledge Index / Session Memory
-> LLM Tool Planner 选择注册过的 safe/read 工具
-> Tool Executor 执行只读工具并将裁剪结果回传 Planner
-> Tool Result Processor 生成 CodeEvidence
-> Context Builder 构造 Context Pack
```

## Context Pack 原则

- 只放入回答当前问题需要的模块、文件、API、流程和证据。
- 具体实现问题必须有通过 Tool Executor 获取的只读工具 evidence。
- 长文件片段需要裁剪。
- 完整文件内容不能直接进入 Context Pack；`read_file` 和 `read_file_chunk` 结果需要先裁剪为 `CodeEvidence.code_snippet`。
- Skill answer prompt 只影响表达结构，不提供事实。
- 回答必须尽量引用文件路径、调用链候选和证据来源。

## 后续扩展

当前只做轻量两层路由。后续可以增加工具级路由、检索重排、跨 Skill 协作和 Reviewer 检查，但不应该破坏 Project Memory / Code Knowledge Index / read-only evidence 的清晰边界。
