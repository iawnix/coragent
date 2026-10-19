---
name: research-memory
description: 持久保存研究问题、尝试、证据、关系和不可变结论，使工作可以带着上下文继续。
---

# 研究记忆

[English version](SKILL.md)

跨轮次保持科学研究连贯时使用本 Skill。Node 保存问题和假设，Job/Artifact 保存执行证据，Result 保存可复用解释。运行时提供 `research-review/1` 投影；需要细节时读取其引用的源记录。

## 核心操作

- `research_read {}` 恢复工作区概览，用返回的 `ref` 读取 Node、Result 或记录。
- `research_search {query}` 按声明的过滤和分页查找历史研究。
- `research_create {goal}` 创建持久问题，可选标题、proposal、plan、关系和来源绑定。
- `research_update {node_id, note}` 记录观察、计划、状态、关系或 assessment 引用。
- `research_result {node_id, conclusion}` 发布带观察、局限、证据引用和文件的不可变结论。

同一问题的重试和参数变化留在一个 Node；独立可解释的分支创建相关 Node，用 `requires`、`part_of` 或 `alternative_to` 连接。用 `task_update action=set_research` 和真实返回的 ID 设置当前任务的 entry/focus Node。

## 证据闭环

收集 Job 后先检查输出，再用 `research_update` 写入科学观察；观察具有独立价值时用 `research_result` 发布，并引用不可变 Artifact/Result，不引用可变工作文件。把测量观察、作者结论和检查引用分开记录。否定或未定结果同样是有效研究记录。

Review 是导航投影：`state_digest` 和 `review_digest` 标明它看到的状态，Node、Result、Job 和 Artifact 才是权威来源。长字段按分页读取，版本冲突后重新读取再替换。工作区路径、版本和不可变文件见[存储与恢复](references/storage.zh-CN.md)，研究拆分见[规划](references/planning.zh-CN.md)，任务控制和 Job 策略见[研究工作流](../research-workflow/SKILL.zh-CN.md)。

## 工作模式

1. 恢复 Review 和当前任务；2. 读取焦点 Node 与证据；3. 由领域 Skill 选择下一项计算或分析；4. 执行后记录变化；5. 发布 Result 或修订计划，同时保留竞争分支和未决问题。

记忆层不从回执推断化学身份或科学有效性；这些解释由领域 Skill 完成，记忆层保存解释及其来源。
