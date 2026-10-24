---
name: research-memory
description: 持久保存研究问题、尝试、证据、关系和不可变结论，使工作可以带着上下文继续。
---

# 研究记忆

[English version](SKILL.md)

跨轮次保持科学研究连贯时使用本 Skill。Node 保存问题、当前计划和明确选定的综合判断，note 留存观察、决策与思路变化，Result 固定值得引用的结论；Job/Artifact 保存执行证据。运行时确定性组装 `research-brief/1`，优先保留已选综合判断，再补充近期 note。持久状态应足以让没有旧聊天历史的模型继续研究；需要细节时读取原始记录。

## 核心操作

- `research_read {}` 恢复工作区概览，用返回的 `ref` 读取 Node、Result 或记录。
- `research_search {query}` 按声明的过滤和分页查找历史研究。
- `research_create {goal}` 创建持久问题，可选标题、plan、关系和来源绑定；假设与调查思路统一写入 `plan`。
- `research_update {node_id, note, references}` 保存带引用的观察；加 `as_assessment:true` 将这条新 note 选为当前判断，可选的 `plan` 修订在同一次操作中提交。
- `research_result {node_id, conclusion}` 发布带观察、局限、证据引用和文件的不可变结论。

先恢复当前任务，读取或搜索相关已有问题，再决定是否创建 Node。准备、计算、验证、重试、调参数和换平台都可以留在同一问题。只有新的研究目标需要独立持续调查和判断时才另建 Node；一个 Result 可独立引用，不代表需要新 Node。新问题用适用的 `requires`、`part_of` 或 `alternative_to` 关系连接。首次 Node 可以提供初始任务绑定，后续创建不会自动加入任务入口或焦点；用 `task_update action=set_research` 和真实返回的 ID 明确维护导航列表。

## 证据闭环

收集 Job 后先检查输出，再选择适用记录：观察、决策或思路调整用 `research_update` 的 note；值得固定并引用的结论用 `research_result`。同一发现不必在两种工具中重复写，也不必再抄成任务进展。每个完成的 Job 不必发布 Result。正式结论引用不可变 Artifact/Result，不引用可变工作文件。区分测量观察、作者结论和检查引用。否定或未定结果同样是有效研究记录。

解释一批新结果、改变研究路线、准备等待或交付时，维护简短的当前综合判断：哪些已确立、哪些仍未解决、证据有哪些限制。保留仍有效的反证和竞争解释，不只描述最后一次 Job。将实际返回的引用放入 `research_update.references`，读取当前 Node 后用 `as_assessment=true` 保存新 note，需要时同时修订 `plan`。笔记、引用、选定与计划在同一事务中完成；读取过期时均不保存，重新读取并判断后再重试。未选定的普通过程笔记不改变当前判断。

`research_result` 的同名 `as_assessment=true` 可原子发布并选定可复用结论。阶段性、负面和未定 Result 都有效，不必等整个研究结束。最新 note 或 Result 从不自动成为当前判断。选择同一 Node 已有的作者记录或 Result 时才用 `assessment_ref`，不要与 `as_assessment=true` 同时提供。同一发现保存在适用记录中，不另写重复的进展文件。

Brief 是导航投影：`state_digest` 和 `brief_digest` 标明它看到的状态，Node、note、Result、Job 和 Artifact 才是权威来源。运行时选择并组装已保存事实，不再调用第二个模型综合摘要。当前判断作为完整单元纳入，放不下时明确要求读取原记录，不推断省略内容。近期 note 只作补充，不因更新较晚而替换已选判断；依赖旧判断前检查新证据复核提示。长字段按分页读取，版本冲突后重新读取再替换。工作区路径、版本和不可变文件见[存储与恢复](references/storage.zh-CN.md)，研究拆分见[规划](references/planning.zh-CN.md)，任务控制和 Job 策略见[研究工作流](../research-workflow/SKILL.zh-CN.md)。

## 工作模式

1. 恢复 Brief 和当前任务。
2. 读取相关已有 Node、当前判断与证据，另开问题前先搜索。
3. 由领域 Skill 选择下一项计算或分析。
4. 用 note 记录有用观察，或用 Result 发布可复用结论；在关键研究阶段选定简短的当前判断，思路改变时修订 plan。
5. 具体下一步由 Task 维护。等待时在同一次 `task_update` 中提供所等 Job 和醒来后的行动，不在 Node plan 或额外进展文件中复制下一步。

发布 Result 时，用 `observation` 记录观察、`conclusion` 记录结论、`evidence_refs` 关联来源记录。恢复研究时，沿这些引用读取支持结论的证据。

发布或修订结论、选择输入与支持引用时，读取[证据与结论](references/evidence.zh-CN.md)。
