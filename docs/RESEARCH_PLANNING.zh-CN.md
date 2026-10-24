# 研究问题图与渐进规划

本文描述当前 Node、Task 和研究上下文的配合方式。运行职责见
[任务与作业架构](TASK_JOB_ARCHITECTURE.zh-CN.md)，证据修订见
[研究证据架构](RESEARCH_EVIDENCE_ARCHITECTURE.zh-CN.md)。

## 如何划分 Node

Node 表示需要持续调查和判断的研究问题。`goal` 保存问题，`plan` 统一保存当前假设与
调查思路，追加式 note 留存观察、决策和思路变化，Result 固定值得引用的结论。
`assessment_ref` 明确选择一条同 Node 的作者记录或 Result，回答当前已知、未知和
证据限制；它不会随最近笔记数量变化而自动更换。

先恢复 Task 的入口和焦点，读取或搜索相关已有问题。只有新的研究目标需要独立持续
调查和判断时才另建 Node。一个操作可以单独执行、一个中间 Result 可以单独引用，
都不足以成为拆分理由。计算步骤、调参数、换平台、初始构型变化、收敛诊断和重复采样
留在所属问题；节点数量与命令数量无固定对应，不预先为每步计算创建节点。

例如“条件 C 下 A/B 哪条反应路线更有利，证据是否充分”可以先保持一个 Node。
优化、TS 候选、频率、IRC、能量和失败重试使用多个 Job；有用的中间结论可以发布
多个 Result。只有某条路线机理或方法适用性本身成为独立研究目标时，才拆出关联 Node。
换程序、构型或下一步计算后原 goal 仍然成立，通常就应复用原问题。不强制一个 Task
只有一个 Node，也不强制一条路线一个 Node。

## 关系与来源

| 关系 | 含义 |
| --- | --- |
| `part_of` | 一个问题属于另一个较大问题；允许共享子问题 |
| `requires` | Agent 声明的研究依赖 |
| `alternative_to` | 需要比较的替代思路 |
| `uses` / `cites` | 从实际材料输入及显式结果引用派生的来源关系 |

关系帮助组织和读取研究，不负责调度 Job。搜索、浏览或相同文件内容不会自动建立实际采用关系。
研究图可以有反馈；每份 Result 引用的是具体历史材料版本。

回溯通过修订 `plan`、追加 note、发布新 Result、显式 `supersedes` 和调整关系完成。
`research_update` 可同时保存 `note`、实际 `references`、可选 `plan`，并通过
`as_assessment=true` 将这条 note 选为当前判断；只增加一次 Node 版本，读取过期时
均不保存。最新 note 或 Result 不自动成为当前综合判断；`research_result` 的同名选项
将发布与选定原子提交。选已有记录用 `assessment_ref`，不能与选新 note 同时提供。
上游修正可产生需复核提示，但不会自动改写下游结论或重算 Job。
Node 的 `closed` 表示结束该问题的活动，不表示科学验证成功。

## Task 关联研究问题

`coragent-user-task/6` 的 research 字段保存两组引用：

- `research.entry_node_ids`：该委托的研究入口。
- `research.focus_node_ids`：当前关注的问题。

Agent 使用 `task_update` 的 `set_research` 同时替换两份列表。首个 Node 可以提供初始
绑定，后续创建不自动加入两份列表；新增问题时明确研究关系，按实际需要维护稳定入口
和当前焦点。引用属于当前工作区，不复制 Node 的计划或状态。创建 Node 和关联 Task
分别在 Research Memory 与 Pi durable 中提交；任务继续使用已保存引用恢复研究。
只读浏览不需要改变焦点。

Task Controller 保存目标、交付条件、下一步、执行计划、可追溯进展、等待和用户控制状态；
科学计划仅由 Node 的 plan 承载，当前判断引用已保存的 note 或 Result，Agent 根据证据
选择研究方向。具体下一次行动只维护在 Task 的 `next_action`；进入等待时必须与所等
Job 一次更新，避免等待新 Job 时仍保留检查旧 Job 的动作。
没有额外的 PlanStep 对象或研究 DAG 调度器。一个会话至多有一个非终态用户任务，
多个任务可以引用共享研究问题。

## 上下文与展示

`GenerationTask.prepareContext` 通过 `research_read(view="brief")` 获取确定性概览。
选择器结合焦点、输入事件、等待 Job、研究入口、直接关系和结论引用，并纳入相关近期
note 与计数；未绑定范围时使用会话内最近活动的一个节点。已选当前判断优先于近期
笔记，结论、限制和引用作为完整单元进入 Brief；放不下时明确要求读取，不展示断开的
数值或省去限制条件的半条判断。不再对投影调用额外模型综合摘要。每次 generation 检查
相关事实，只有首次、范围变化、事实变化或失败读取后的重试才追加上下文。
Brief 是派生阅读视图，note 不会因进入摘要就晋升 Result 或被选为综合判断；选定后
出现新结果或相关终态 Job 时提示需要复核，不自动改写科学判断。
详细规则见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。

Monitor 任务详情使用 `research-snapshot/3` 的局部图展示入口、焦点、计划摘录和相关 Job。
这是界面的读取投影，与供模型使用的 `research-brief/1` 用途不同。
省略项通过 `research_read`、`research_search`、`task_read` 和 `job_status` 继续读取。

## 进展与交付

解释一批新结果、改变研究路线、准备等待或交付时，Agent 应更新简短的当前判断，
保留仍有效的早期发现、反证、竞争解释和未解决问题，并引用具体证据。普通操作可只
追加未选定的过程 note；可复用的阶段性、负面或不确定结论都可以发布为 Result。
同一发现按用途写入 note 或 Result，不必两处重复写，也不必再抄成任务进展或 memory 文件。
现有工具将 Result 身份、Artifact 内容摘要和归属 Job 执行里程碑用于任务进展跟踪，
任务下一步和等待控制仍由 Agent 明确维护。
重复查询、改写计划、追加笔记、创建节点或切换焦点本身不计为新证据。
这些记录用于持续推进，不判断新证据的科学价值。

Task 完成需要交付条件的证据和最终回复交付。所有 Node 关闭或所有 Job 成功都不能代替
这一步；已交付任务关联的共享 Node 可以继续开放。用户预算仍应保留在要求和计划中，
当前没有安装级的结构化花费预算执行器。

Node 使用 `research-node/2`，Task 使用 `coragent-user-task/6`。运行时、合同与 Skill
必须同步部署；旧字段和旧版本没有兼容别名、并行协议或自动迁移。

相关实现为 `apps/agent/tasks/controller.mjs`、`apps/agent/context/manager.mjs`
和 `backend/src/research_agent/research/brief_selection.py`。
验收包含清空聊天历史后的研究恢复、关键反证不随近期笔记退出、原子保存与过期读取
回滚、等待和下一步的一致性。确定性行为由 `tests/node/native/task-controller.test.mjs`、
`tests/node/native/context-manager.test.mjs`、`tests/unit/test_research_context.py`
及 Worker 研究流测试覆盖；真实模型的规划质量需要独立评估。
