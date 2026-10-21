# 任务生命周期

使用 `runtime_control` 中真实的 submission ID，不编造 ID，也不使用研究 `user_*` 引用、引用历史或 Monitor 事件代替用户提交。更新状态前用 `task_read` 获取当前 `expected_revision`。除非用户修改范围，后续指令继续属于当前委托。

## 等待与阻塞

Job 运行期间继续独立的已授权工作。遵循 `job_status` 返回的查询间隔；独立工作耗尽后登记当前任务的实际 Job，并结束本轮：

```json
{"expected_revision":3,"action":"wait","wait":{"job_ids":["<返回的 job_id>"],"mode":"all"}}
```

根据哪些完成事件能够推进下一步，选择 `all` 或 `any`。Monitor 提供执行事实；唤醒后检查任务、相关 Job 和当前指令。进程结束仍需收集与科学检查。不要反复读取无变化的状态或日志，也不要每次唤醒都发送相同进展。

缺少结果或方法尚不确定属于待办。宣布研究受阻前，先检查可用输入，选择有界的初步实验。只有没有其它可独立推进的已授权工作时才使用 `action=block`。传入 `block_kind`、说明为何无法继续的具体 `reason`，以及解除阻塞所需的 `resume_when`。`execution_failure`、`budget_exhausted`、`scientific_dead_end` 和 `resource_unavailable` 必须带 `evidence_refs`。`missing_user_input` 仅适用于现有来源无法提供的必要信息，不适用于可选偏好或未完成分析。

一个候选失败不等于整个委托受阻。无进展轮数提示重新评估方法，不是固定停止阈值。新用户指令解决阻塞时，用 `refine` 引用真实 `source_submission_ids`；`progress` 本身不恢复阻塞任务。

## 用户暂停、恢复与取消

确认执行情况前，先持久化当前真实用户指令：

```json
{"expected_revision":3,"action":"apply_user_control","control":"pause","source_submission_ids":["<真实 submission ID>"]}
```

- `pause` 保留已有 Job。若用户同时要求取消部分 Job，再对它们调用 `job_cancel`。
- `cancel` 必须明确 Job 策略：停止运行中的计算用 `jobs=cancel`，用户要求保留计算用 `jobs=keep`。检查返回的取消回执。
- `resume` 必须来自新的真实用户指令。读取任务、内部续接和 Monitor 事件都不是授权。恢复部分交付任务时，历史保留原来的验收结果。

取消 Job 或关闭 Node 不会自动停止任务。确认持久化的任务状态和要求取消的 Job 后，才能声称工作停止；取消待处理或未知时如实说明。写入停止状态后，只进行只读核实、用户要求的 Job 取消和最终确认。取消无需完成评估，也不代表研究成功。迟到事件不能恢复已停止工作。

## 执行与交付恢复

`execution_recovery` 单独记录 Agent 执行故障，与科学阻塞分开。决定下一步前检查恢复状态和已有 Job/交付回执。核实已完成或不确定的外部工作；不能因运行或 Memory 更新失败而重复执行。说明需要处理的执行故障；新指令解决问题时可用 `refine`，用户也可通过 Monitor 显式恢复。

最终回复恢复沿用已保存的完成证据和回执。只做只读核实与最终回复，不启动新计算或重复发送外部消息。如果完成证据失效且控制器将任务返回活跃状态，按[验收流程](acceptance.zh-CN.md)重新评估受影响条件。
