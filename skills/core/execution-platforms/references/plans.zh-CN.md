# 多平台任务执行

同一个研究 Task 包含多个工作项，每个 Job 固定一个平台与入口。这不表示把一个紧耦合 MPI
进程自动拆到互不相通的集群。

未绑定的 Task 实际需要计算时，通过 `task_update action=bind_execution` 指定默认位置和明确允许的位置：

```json
{
  "action": "bind_execution",
  "expected_revision": 1,
  "execution_target": {"platform": "Com30", "scheduler_entry": "qrun"},
  "execution_intent": {"source_submission_id": "1", "source_text": "在 Com30 用 Qrun"},
  "execution_policy": {
    "placements": [
      {"target": {"platform": "Com30", "scheduler_entry": "qrun"},
       "intent": {"source_submission_id": "1", "source_text": "在 Com30 用 Qrun"}},
      {"target": {"platform": "FEDCluster", "scheduler_entry": "tri"},
       "intent": {"source_submission_id": "1", "source_text": "在 FEDCluster 用 Tri"}}
    ],
    "max_in_flight": 4,
    "max_attempts": 100
  }
}
```

修订号替换为当前 Task 的实际版本，来源必须引用该任务用户提交中实际存在的原文，
默认位置必须包含在允许位置中，不能虚构授权。已明确需要计算时，task_begin 也可接收相同的
execution 字段；普通研究任务创建时省略这些字段。

通过 task_update action=set_execution_plan 设置 execution_plan.items。每项必填 id、work_id
和 resources（cpus、memory_mb），可选 target、depends_on、input_artifact_ids。
depends_on 引用工作项 ID，不能有循环或不存在的依赖。省略 target 使用策略默认位置。
计划修订不能修改或移除已提交、已完成的项。
未绑定任务的首次 set_execution_plan 可同时传入 execution_target、execution_intent、execution_policy，
将绑定与计划一起保存；省略时在用户原始要求约束下解析配置默认位置。计划失败不会留下半完成绑定。
已绑定任务沿用已有策略；需要变更时，在建计划前先用 refine 和新用户来源修改。已有计划固定其位置策略。

使用 task_update action=select_execution_item 和 execution_item_id 选择可执行项。
准备命令会获得可信 CORAGENT_TASK_EXECUTION 上下文，普通 bash 仍在本机执行。
使用该项的工作身份、输入 Artifact 和资源准备，原样提交请求。
运行时检查这些约束、任务／入口在途限额和累计尝试预算；unknown Job 仍占名额。

通过 task_read 的 execution_progress 查看 ready／blocked 项及其 Job 状态。
在预算内推进独立可执行项；剩余工作都等待 Job 时使用现有任务等待流程。
提交结果不明时用 job_reconcile 核对原 Job，不能换请求 ID 再提交。

运行成功后收集输出，发布科学验证 Result，再以 task_update action=complete_execution_item
提交 execution_item_id、artifact_ids 和包含该 Result 的 evidence_refs。
只能交接该项 Job 收集得到的 Artifact。后继上下文将要求这些 Artifact 作为输入，
准备器会自动暂存核验后的内容到 inputs/artifacts/<artifact_id>/payload。
验证 Result 的 inputs 或 evidence_refs 必须引用每个交接 Artifact。收集或传输失败只需重试收集，不重跑科学计算。
仅有退出码成功不能放行依赖。

暂停停止新派发；取消区分保留 Job 和请求终止 Job。计划修订保留已提交工作和证据。
有意重算建立新的工作项与 work_id；相同计算还须遵守 job_start 既有 repeat 的前驱、原因与预算合同。

可选自动放置使用 execution_policy.automatic_placement=true，工作项提供 backend 和 candidates，
不同时提供 target。所有候选必须属于固定策略，且软件绑定存在、CPU／内存空闲量已知并足够。
选择排除暂停／过期观测，并计入本次计划先前放置的资源，记录 placement_reason；准备时继续验证软件。
GPU 和现有非 Qrun handler 的可用容量未知，不能据此自动放置；这类入口可显式选择。
max_in_flight 约束工作区内的提交，跨工作区共享资源仍由原调度器／Qrun 统一管理。
