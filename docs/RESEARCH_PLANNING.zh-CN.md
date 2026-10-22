# 研究问题图与渐进规划

本文描述当前 Node、Task 和研究上下文的配合方式。运行职责见
[任务与作业架构](TASK_JOB_ARCHITECTURE.zh-CN.md)，证据修订见
[研究证据架构](RESEARCH_EVIDENCE_ARCHITECTURE.zh-CN.md)。

## 如何划分 Node

Node 表示可以独立推进和解释的研究问题。`goal` 保存问题，`proposal` 保存可选假设，
`plan` 保存调查方法，`progress` 保存当前解释。结果通过不可变 Result 发布。

两部分有独立结论、可以分别暂停或比较、需要被多个问题复用时，可以拆成不同 Node。
同一问题的参数调整、初始构型变化、收敛诊断和重复采样通常留在原 Node。
节点数量和命令数量没有固定对应关系；不要求总根节点或预先建好完整计划。

例如研究两条竞争路线时，可以分别保存两条路线的问题，并共享同一个中间体研究。
某条路线失败后，在原问题中保留证据并修订方法；无需复制所有节点或删除失败尝试。

## 关系与来源

| 关系 | 含义 |
| --- | --- |
| `part_of` | 一个问题属于另一个较大问题；允许共享子问题 |
| `requires` | Agent 声明的研究依赖 |
| `alternative_to` | 需要比较的替代思路 |
| `uses` / `cites` | 从实际材料输入及显式结果引用派生的来源关系 |

关系帮助组织和读取研究，不负责调度 Job。搜索、浏览或相同文件内容不会自动建立实际采用关系。
研究图可以有反馈；每份 Result 引用的是具体历史材料版本。

回溯通过修订 `proposal/plan/progress`、记录新 Result、显式 `supersedes`
和调整关系完成。上游修正可产生需复核提示，但不会自动改写下游结论或重算 Job。
Node 的 `closed` 表示结束该问题的活动，不表示科学验证成功。

## Task 关联研究问题

`coragent-user-task/3` 保存两组引用：

- `research.entry_node_ids`：该委托的研究入口。
- `research.focus_node_ids`：当前关注的问题。

Agent 使用 `task_update` 的 `set_research` 同时替换两份列表。引用属于当前工作区，
不复制 Node 的计划或状态。创建 Node 和关联 Task 分别在 Research Memory 与 Pi durable
中提交；任务继续使用已保存的引用恢复研究。只读浏览不需要改变焦点。

Task Controller 保存目标、交付条件、等待和用户控制状态；Agent 根据证据选择研究方向。
没有额外的 PlanStep 对象或研究 DAG 调度器。一个会话至多有一个非终态用户任务，
多个任务可以引用共享研究问题。

## 上下文与展示

`GenerationTask.prepareContext` 通过 `research_read(view="brief")` 获取确定性概览。
选择器结合焦点、输入事件、等待 Job、研究入口、直接关系和结论引用；未绑定范围时使用
会话内最近活动的一个节点。每次 generation 检查相关事实，只有首次、范围变化、事实变化
或失败读取后的重试才追加上下文。详细规则见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。

Monitor 任务详情使用 `research-snapshot/3` 的局部图展示入口、焦点、计划摘录和相关 Job。
这是界面的读取投影，与供模型使用的 `research-brief/1` 用途不同。
省略项通过 `research_read`、`research_search`、`task_read` 和 `job_status` 继续读取。

## 进展与交付

Result 身份、Artifact 内容摘要和归属 Job 的执行里程碑用于记录任务进展。
重复查询、改写计划、追加笔记、创建节点或切换焦点本身不计为新证据。
这些记录用于持续推进，不判断新证据的科学价值。

Task 完成需要交付条件的证据和最终回复交付。所有 Node 关闭或所有 Job 成功都不能代替
这一步；已交付任务关联的共享 Node 可以继续开放。用户预算仍应保留在要求和计划中，
当前没有安装级的结构化花费预算执行器。

相关实现为 `apps/agent/tasks/controller.mjs`、`apps/agent/context/manager.mjs`
和 `backend/src/research_agent/research/brief_selection.py`。
确定性行为由 `tests/node/native/task-controller.test.mjs`、
`tests/node/native/context-manager.test.mjs`、`tests/unit/test_research_context.py`
及 Worker 研究流测试覆盖；真实模型的规划质量需要独立评估。
