---
name: batch-schedulers
description: 配置 Qrun、TRI、PBS、Torque 和 Slurm 执行目标，转换资源请求，诊断提交、排队、取消、记账和恢复。
---

# 批处理调度器接入

## 脚本路由

按下表选择 handler，并读取对应调度器参考。handler 都只依赖 Python 标准库：stdin 接收请求 JSON，stdout 返回回执或状态 JSON。随附脚本路径相对于本 Skill 目录；Qrun 使用执行主机上安装的独立程序。

| 调度器 | 入口 | 说明 |
| --- | --- | --- |
| Qrun | 已安装的 `qrun handler` | [Qrun](references/qrun.zh-CN.md) |
| TRI | `scripts/tri.py` | [TRI](references/tri.zh-CN.md) |
| PBS | `scripts/batch.py pbs` | [PBS](references/pbs.zh-CN.md) |
| Torque | `scripts/batch.py torque` | [Torque](references/torque.zh-CN.md) |
| Slurm | `scripts/batch.py slurm` | [Slurm](references/slurm.zh-CN.md) |

所有 handler 通过相同外部 Job 协议实现 `probe`、`submit`、`status`、`cancel`、`recover`。安装配置用 `execution.platforms.<platform>.schedulers.<entry>.handler` 选择脚本，并声明匹配的 `executor`。科学 Skill 负责方法和软件后端；[research-workflow](../research-workflow/SKILL.zh-CN.md) 解析并固定执行目标。普通计算通过 `job_start`、`job_status`、`job_reconcile`、`job_cancel`、`job_collect` 管理。

## 配置提交位置和资源

确认提交账户、共享工作目录和软件路径。在提交主机上使用 `transport="local"`，从其它机器连接则使用 `transport="ssh"`；它决定 handler 在哪里运行，Qrun 在该主机直接执行；集群调度器再选择计算节点。[目标配置](references/targets.zh-CN.md) 说明配置结构和文件模式；原生命令与恢复证据按对应调度器说明配置。

根据程序并行能力申请 CPU，根据工作集申请内存，根据代表性计算估计时限。Qrun 在单个 FIFO 池中预留 CPU 和内存，使用数字作业编号，分别观察预算与实际用量；TRI 按节点和资源分配任务，无需 PBS/Slurm 式队列选择；PBS 使用 `select`，Torque 使用 `nodes:ppn`，Slurm 使用 CPU/内存/GPU 参数。调整请求前检查等待原因和站点限制。队列连接配置放在 `handler_environment`，计算程序环境放在所选软件后端绑定中。

## 观察与恢复

从 Job 回执的目标和 `scheduler_id` 定位原生证据。区分提交接受、排队、运行、终态记账与输出收集。提交响应不确定时恢复原请求身份；一次查询未找到任务不能证明从未提交。取消后核实执行已经停止。

失败时结合调度记账、`logs/scheduler.stdout`/`logs/scheduler.stderr` 和计算日志。[Qrun 资源与作业诊断](references/qrun.zh-CN.md)、[TRI 诊断](references/tri-diagnosis.zh-CN.md)及 [PBS/Torque/Slurm 命令](references/commands.zh-CN.md)说明原生证据。修改 handler 后，用确定性测试或已授权测试队列验证提交、终态记账、取消及响应丢失恢复。

TRI 服务端安装、客户端注册、容量配置、数据库维护和升级属于基础设施管理，参阅 [TRI 运维](../../../docs/TRI_OPERATIONS.zh-CN.md)。逐节点软件验收见 [TRI 接入](references/tri.zh-CN.md)。

平台、连接、环境与存储配置统一见 [execution-platforms](../execution-platforms/SKILL.zh-CN.md)。
