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

## Job Manager

jobs/manager.py 提供唯一的 job_* 执行方法，由平台适配器处理实际进程和调度系统。
application/job_manager.py 管理状态观察与持久事件，host/jobs/worker.mjs 运行后台轮询和投递。
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

这次调整是单协议切换，Host 使用 coragent-host/3，旧客户端必须同步更新：旧 producer=monitor、旧内部 monitor-wake、旧 JobRuntime 导入、
旧研究 Review 接口不提供别名。未完成的旧输入不接受无来源或无原因的恢复；旧 Task 文档需要
匹配当前版本，否则明确拒绝。不会修改已安装服务或现存用户数据库，也不提供隐式转换。
升级前应结束旧执行，保留原研究记录，并在新会话中显式绑定既有研究节点。
Job 观察的持久登记与投递格式保持原有唯一合同，不引入另一套作业状态库。
