# 任务、作业与执行

| 名称 | 职责与状态所有者 |
| --- | --- |
| Task Controller（任务控制器） | 用户任务的继续、等待、暂停、取消与完成；状态保存在 Pi durable |
| Job Manager（作业管理器） | 作业提交、跟踪、取消、核对、收集及可靠事件投递；持久事实在作业记录中 |
| Research Memory（研究记忆库） | 研究要求、节点、结果、关系与证据 |
| Agent Runtime（Agent 执行引擎） | Pi 会话、模型和工具循环、压缩与恢复 |
| Monitor（管理面板） | 统一查看和控制上述工作；使用既有 monitor/* API |

Task 是用户目标，Run 是一次输入启动的 Agent 执行，Job 是外部计算。
Pi generation/tool task 只在诊断中称为内部执行单元，不是用户 Task。

## Task Controller

`task_begin` 登记持续委托，`task_read` 读取完整任务，`task_update` 修订任务、
记录进展、等待 Job 或提出完成。普通问答不自动建立任务。每个会话至多有一个
非终态任务，状态保存在 SessionWorker 的 Pi durable 文档中。

Task 保存 objective、criteria、next_action、execution_plan、进展依据和控制状态。
科学假设与调查方案只写在对应 Node 的 plan，过程决策写入 note；Task 不保存第二份
科学计划。同一发现按用途记录为 note 或 Result，不必再重复成任务进展说明。

| 状态 | 含义 |
| --- | --- |
| active | 可以继续推进 |
| waiting | 等待指定归属 Job 满足条件 |
| paused | 用户暂停自动推进 |
| blocked | 需要输入、资源或其他外部条件 |
| completing | 已提出有证据的完成条件，等待最终回复成功交付 |
| completed | 完成条件与最终回复已结算 |
| cancelled | 用户取消委托 |

控制器在执行变化和周期核对时检查任务；没有新的 Job 事件也能续接活跃任务。
用户输入优先。暂停允许当前回复和已有 Job 收尾；取消任务明确选择保留或请求取消 Job。
临时执行故障可触发有限自动重试，需人工处理的故障保存在恢复记录中。
`execution_recovery` 用 `failure_domain` 和 `failure_kind` 保存故障来源，
当前 Agent 输入失败归属 `agent_runtime`，区分 `provider_quota`、`provider_error`、
`context_limit`、`runtime_blocked`、`agent_fault` 和未分类的 `runtime_error`。
日配额等明确额度耗尽直接进入 `attention_required`，普通 429 限流仍按有界退避恢复。
恢复事件以 `runtime_failure` 保存归因和原始 `submission_id`，恢复记录清除后仍可审计。
这些记录不改变已有 Job 状态，也不证明计算提交失败。Task 的 `block_kind` 表示阻塞影响：
当仍有对应配额恢复记录，且 Agent 用明确配额错误作为 `execution_failure` 的理由时，
控制器将其规范为 `resource_unavailable` 并保留来源；独立的 Job 故障不继承模型配额归因。
旧恢复记录可按原始 `reason/detail` 识别，无需重写会话数据库；外层状态展示保持简洁。
运行时通过现有工具观察 Result、Artifact 和归属 Job 里程碑并记录进展，单纯改计划或
重复查询不计为新证据；下一步、等待和控制仍由 Agent 明确维护。

任务控制与作业取消通过同一 Monitor 界面操作，具体命令见[终端](TERMINAL.zh-CN.md)。
研究入口和焦点见[研究规划](RESEARCH_PLANNING.zh-CN.md)。

## Job Manager

`backend/src/research_agent/jobs/manager.py` 提供唯一的 `job_*` 执行方法，
由平台适配器处理实际进程和调度系统。
`backend/src/research_agent/application/job_manager.py` 管理状态观察与持久事件，
`apps/agent/host/jobs/worker.mjs` 运行后台轮询和投递。
后台进程是 Job Manager 的内部工作部分，不作为另一个 Observer/Controller 对外暴露。
普通排队和运行状态变化被记录；结束、失败、状态未知或排队超时可产生需要处理的事件。

## 两条推进路径，一套任务策略

作业事件和任务自动续接都经过 SessionWorker 的 Task Controller 策略以及 Pi 输入接纳事务。
事件先检查任务归属、等待条件和暂停状态；任务续接检查任务是否未完成、是否空闲、是否等待或阻塞。
已有用户输入优先，同一会话的自动输入预留防止两条路径同时启动重复执行。
没有新 Job 事件时，活跃且空闲的任务仍可继续分析或交付。
等待状态也通过同一控制器核对真实 Job 状态，不能由模型摘要直接解除。

输入接纳是 Agent Runtime 内部机制：验证来源、幂等、忙碌策略和控制状态，原子提交输入及来源记录。
它不是另一套调度器，也不是模型 token 预算检查。

| producer | 执行来源 | reason |
| --- | --- | --- |
| user | 用户 | user_message |
| job_manager | 作业事件投递 | job_event |
| task_controller | 任务推进 | task_continue / execution_retry / final_response_retry |

producer 与 reason 都由运行时验证，参与幂等身份。Monitor 的执行列表显示原因，
不能通过普通用户文本伪造内部事件。研究上下文根据相关事实版本刷新，独立于 producer。
详见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。

## 升级边界

当前 Host 使用 `coragent-host/3`，旧客户端必须同步更新：旧 producer=monitor、旧内部 monitor-wake、旧 JobRuntime 导入、
旧研究 Review 接口不提供别名。Task 使用 `coragent-user-task/6`，Node 使用 `research-node/2`；
运行时、合同与 Skill 必须同步部署。未完成的旧输入不接受无来源或无原因的恢复；旧 Task/Node
格式明确拒绝，没有字段别名、隐式转换或并行协议。升级前应结束旧执行并保留原研究记录；
旧格式不自动迁移，需新建工作区并显式导入有用材料，不能直接绑定旧格式节点。
Job 观察的持久登记与投递格式保持原有唯一合同，不引入另一套作业状态库。

源码验证入口见[测试运行器](../tools/test/README.md)。重点覆盖输入来源、重复投递、
忙碌与暂停竞争、Job 等待、故障恢复及最终回复结算；科学结论正确性需要独立证据。
