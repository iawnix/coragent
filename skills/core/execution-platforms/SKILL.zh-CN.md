---
name: execution-platforms
description: 选择命名计算平台与调度入口，查询资源，准备本机、SSH 或多平台任务的软件环境及成果交接。调度器具体操作使用 batch-schedulers，科学规划与验证使用 research-workflow。
---

# 计算平台

使用 `job_platforms` 发现已配置的平台与调度入口。平台管理连接、公共软件环境和存储；
入口选择调度实现。`local`／`ssh` 表示到达提交端的方式，与 `tri`、`qrun`、`pbs`、
`torque`、`slurm`、`external` 独立。

使用 `execution_target: {"platform":"Com30","scheduler_entry":"qrun"}` 选择位置。
不需要另配 `com30_qrun` 标签。省略入口表示使用该平台的默认入口。
名称与别名统一由 `job_resolve_target` 解析；歧义或不可用入口必须在提交前解决。
平台繁忙不代表获准把计算或数据移到其他平台。

`job_resources` 返回调度器能提供的容量与用量，未知值不是零，快照不保证作业立即获准运行。
`job_probe` 检查基础设施，不证明科学软件可用。准备前使用软件环境检查器；需要确认计算节点环境时，
提交实际的最小检查 Job。

普通 bash 始终在控制端执行。科学作业使用
`python -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --platform Com30 --scheduler-entry qrun ...`
准备。`--executor` 选择科学步骤，`--backend` 选择脚本使用的软件绑定，二者都不是调度入口选择参数。
将返回的请求文件与摘要原样交给 `job_start`。

配置平台及继承的软件／存储设置时，阅读[配置说明](references/configuration.zh-CN.md)。
同一任务分散到多个平台时，先阅读[执行计划](references/plans.zh-CN.md)。
队列具体行为见 [batch-schedulers](../batch-schedulers/SKILL.zh-CN.md)。安装与服务归属由主安装器和普通运维文档说明。
