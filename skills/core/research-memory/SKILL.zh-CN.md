---
name: research-memory
description: 持久保存研究问题、尝试、证据、关系和不可变结论，使工作可以带着上下文继续。
---

# 研究记忆

[English version](SKILL.md)

跨轮次保持科学研究连贯时使用本 Skill。Node 保存问题和当前计划，note 留存观察、决策与思路变化，Result 固定值得引用的结论；Job/Artifact 保存执行证据。运行时提供包含近期 note 和来源引用的 `research-brief/1` 投影；需要细节时读取原始记录。

## 核心操作

- `research_read {}` 恢复工作区概览，用返回的 `ref` 读取 Node、Result 或记录。
- `research_search {query}` 按声明的过滤和分页查找历史研究。
- `research_create {goal}` 创建持久问题，可选标题、plan、关系和来源绑定；假设与调查思路统一写入 `plan`。
- `research_update {node_id, note}` 记录观察、计划、状态、关系或 assessment 引用。
- `research_result {node_id, conclusion}` 发布带观察、局限、证据引用和文件的不可变结论。

先恢复当前任务，读取或搜索相关已有问题，再决定是否创建 Node。准备、计算、验证、重试、调参数和换平台都可以留在同一问题。只有新的研究目标需要独立持续调查和判断时才另建 Node；一个 Result 可独立引用，不代表需要新 Node。新问题用适用的 `requires`、`part_of` 或 `alternative_to` 关系连接。首次 Node 可以提供初始任务绑定，后续创建不会自动加入任务入口或焦点；用 `task_update action=set_research` 和真实返回的 ID 明确维护导航列表。

## 证据闭环

收集 Job 后先检查输出，再选择适用记录：观察、决策或思路调整用 `research_update` 的 note；值得固定并引用的结论用 `research_result`。同一发现不必在两种工具中重复写，也不必再抄成任务进展。每个完成的 Job 不必发布 Result。正式结论引用不可变 Artifact/Result，不引用可变工作文件。区分测量观察、作者结论和检查引用。否定或未定结果同样是有效研究记录。

最新 Result 不自动成为 Node 的当前综合判断。只有新结论代表这一判断时才设置 `as_assessment=true`；发布和选定在同一事务中完成，读取过期时两者均不保存。重新读取 Node 并判断后再重试。普通发布不改变已选综合判断。

Brief 是导航投影：`state_digest` 和 `brief_digest` 标明它看到的状态，Node、note、Result、Job 和 Artifact 才是权威来源。近期 note 摘录与计数帮助恢复过程，不会发布结论或选定综合判断。长字段按分页读取，版本冲突后重新读取再替换。工作区路径、版本和不可变文件见[存储与恢复](references/storage.zh-CN.md)，研究拆分见[规划](references/planning.zh-CN.md)，任务控制和 Job 策略见[研究工作流](../research-workflow/SKILL.zh-CN.md)。

## 工作模式

1. 恢复 Brief 和当前任务；2. 读取相关已有 Node、近期 note 与证据，另开问题前先搜索；3. 由领域 Skill 选择下一项计算或分析；4. 用 note 记录有用观察或决策，或用 Result 发布可复用结论，思路改变时修订 plan；5. 按需更新任务导航、下一步或等待状态，保留竞争解释和未决问题。

发布 Result 时，用 `observation` 记录观察、`conclusion` 记录结论、`evidence_refs` 关联来源记录。恢复研究时，沿这些引用读取支持结论的证据。

发布或修订结论、选择输入与支持引用时，读取[证据与结论](references/evidence.zh-CN.md)。
