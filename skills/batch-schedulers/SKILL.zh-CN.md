---
name: batch-schedulers
description: 配置 PBS、Torque 和 Slurm 执行目标，选择批处理资源，使用原生命令提交任务，并诊断队列和记账结果。
---

# PBS、Torque 与 Slurm 运维

## 脚本路由

调用仓库脚本前先看[脚本路由地图](../../docs/skill-script-routing.zh-CN.md#batch-schedulers)。地图列出支持的入口和接口；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式。

**入口：** `skills/batch-schedulers/scripts/queue.py`（stdin/子命令合同见脚本地图）。

连接已有批处理集群，或排查提交、排队、取消和已完成任务时使用本 Skill。

## 选择提交位置和资源

确认调度器类型、提交账户、队列/分区、共享工作目录和应用环境。CoRAgent 位于
登录节点时选择本机连接，位于其它机器时选择 SSH。计算节点需要能访问提交脚本
中的同一绝对工作路径和应用路径。

根据程序并行能力选择 CPU，根据实际工作集选择内存，根据代表性计算估计运行
时限。调整请求前先检查队列限制和等待原因。PBS 使用 `select`，Torque 使用
`nodes:ppn`，Slurm 使用 CPU、内存和 GPU 参数。

## 接入随附脚本

[目标配置与恢复](references/targets.zh-CN.md) 提供完整配置及部署检查。
[queue.py](scripts/queue.py) 仅依赖 Python 标准库，首个参数选择 `pbs`、`torque`
或 `slurm`，从标准输入读取一条外部 Job 请求，在标准输出返回 JSON 回执或状态。

脚本实现 `probe`、`submit`、`status`、`cancel`、`recover`，提交日志保存在执行
目录的 `.coragent/` 下。CoRAgent 通过所选连接方式准备输入、保存 Job 回执并收集
声明的输出。普通计算通过配置好的 Job 目标提交。

## 检查原始证据

[调度命令与诊断](references/commands.zh-CN.md) 说明资源参数、原生查询和历史
记录要求。排队时检查等待原因和资源限制；失败时结合记账退出码、调度器日志与
计算日志；提交响应丢失时使用稳定请求身份协调原 Job。

站点专有的资源参数在脚本中调整，并同步记录队列规则。部署修改时在测试队列
检查提交、终态记账、取消及响应丢失后的恢复。
