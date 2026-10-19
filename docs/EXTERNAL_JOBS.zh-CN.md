# 通过文档与命令接入外部任务

[English](EXTERNAL_JOBS.md)

外部执行目标允许 Skill 或安装环境提供队列所需的小型命令桥接程序。
CoRAgent 管理 Job 身份、持久回执、文件暂存、重启恢复与结果收集；桥接程序
负责原生提交语法和状态解释。它是可执行程序，无需作为 Python 插件导入
CoRAgent 进程。

## 配置执行目标

CoRAgent 与队列命令都部署在登录节点时：

```toml
[execution]
default_target = "compute"

[execution.targets.compute]
driver = "external"
transport = "local"
cluster_name = "compute"
work_root = "/absolute/shared/coragent-jobs"
handler = ["/usr/bin/python3", "/absolute/coragent/skills/tri-operations/scripts/queue.py"]

[execution.targets.compute.handler_environment]
TRI_SOCKET = "/absolute/runtime/tri/server.sock"

[execution.targets.compute.submission.resources]
cpus = 4
memory_mb = 4096
```

将示例路径替换为本次安装的实际路径，并创建 `work_root`。科学软件配置与
其它目标一样放在 `execution.targets.compute.bindings` 中。`transport="local"`
表示提交命令在 CoRAgent 所在主机执行，计算节点由队列分配。多个本机命令
目标可以与直接执行的 process/systemd 目标共存，并分别指定集群名称。

从另一台主机提交时，将 `transport` 改为 `ssh`，设置 `ssh_host`，按需指定
`ssh_config`。此时 `handler` 与 `work_root` 是该主机上的路径。SSH 目标通过
rsync 暂存和收集文件；本机目标在控制端 Job 目录与 `work_root` 之间复制。
计算节点需要能以相同路径访问该目录，共享挂载由部署环境提供。
本机进程使用内置 process/systemd 驱动，批处理队列使用外部脚本。
Python 调度器插件加载机制已移除。

`handler_environment` 配置提交命令的环境，与计算程序环境分开。
凭据优先沿用已有受保护的服务/连接配置。Job 保存目标配置摘要；修改连接地址
或桥接程序后，原 Job 不会被悄悄指向新目标。恢复原目标配置后继续核对任务。

## 桥接协议

CoRAgent 按 argv 执行 `handler`，通过 stdin 发送一个 JSON 对象，接收 stdout
上的一个 JSON 对象及零退出码。诊断输出到 stderr。请求与响应均包含
`schema_version: "coragent-external-job/1"`，同一程序处理以下 `action`：

| 操作 | 输入 | 必需响应 |
| --- | --- | --- |
| `probe` | 协议版本和操作名 | 布尔值 `available`，可附 `error` |
| `submit` | 稳定的 `request_id`、`job_id`、执行目录 `cwd`、绝对路径 `script`、`resources`、可选 `queue`、有效 `timeout_seconds` | 非空字符串 `scheduler_id` |
| `status` | 原始提交字段及 `scheduler_id` | 对应的 `scheduler_id`、统一的 `state`、退出/结束证据 |
| `cancel` | 原始提交字段及 `scheduler_id` | 对应的 `scheduler_id`、布尔值 `accepted` |
| `recover` | 原始提交字段及稳定的 `request_id` | 已有的 `scheduler_id`，或确切查无记录后的 `found: false` |

运行脚本已经包含计算 argv、环境、stdin、超时和 stdout/stderr 重定向。
在给定 `cwd` 中提交该脚本即可。计算日志写入 `logs/`，退出证据写入执行目录。
外部 Job 会保留调度器分配的 GPU 可见性，Job 运行时使用桥接程序的观察确定终态。

状态包括 `submitted`、`queued`、`held`、`running`、`succeeded`、`failed`、
`cancelled`、`timed_out` 和 `unknown`。终态响应需要 `execution_finished: true`，
成功还需要整数 `exit_code: 0`。可选字段为 `started_at`、`finished_at`、`error`
及对象类型的 `diagnostics`。收到取消回执后继续观察状态；执行尚未停止时返回非终态。

```json
{"schema_version":"coragent-external-job/1","scheduler_id":"42","state":"succeeded","exit_code":0,"execution_finished":true,"diagnostics":{"node":"compute-a"}}
```

`recover` 使用提交前记录的稳定身份进行查找。提交响应丢失后，`job_reconcile`
调用它恢复已有任务，不重新提交。服务不可用、响应损坏或结果不明确时保持未知。
原生幂等标识/工作流标识使用传入的 `request_id`，以区分不同工作区、不同目标
中的相同 Job 编号。

## 编写 Skill 与扩展

资源选择、作业脚本约定和原生命令用法写在 Skill 中。需要持续观察时，通过
小型辅助程序转换成上述协议；辅助程序可以使用任何可执行语言。

随附的 [TRI 脚本](../skills/tri-operations/scripts/queue.py) 调用 `tri_sub`、
`tri_stat` 和 `tri_del`，通过 TRI 外部身份恢复任务。
[使用说明](../skills/tri-operations/references/coragent-jobs.zh-CN.md) 提供命令路径覆盖和节点选择方法。

随附的 [batch-schedulers](../skills/batch-schedulers/SKILL.zh-CN.md) 提供 PBS、Torque
和 Slurm 命令脚本。[目标配置说明](../skills/batch-schedulers/references/targets.zh-CN.md)
涵盖命令、历史记账要求和持久提交恢复。调度器差异在脚本和相应文档中维护。

原来的 `pbs`、`torque`、`slurm`、`tri` 及远程 `process` 驱动配置需改为
`driver="external"`，并指定连接方式和脚本 argv。旧 Python 插件包、注册表和
适配类接口已删除。已有任务先在旧安装中收集完成再迁移，旧回执不做转换。

验证新辅助程序时覆盖排队、运行、成功、失败、超时、取消，以及控制端重启和
提交响应丢失。检查从独立执行目录收集声明输出的过程。使用隔离队列或确定性
命令模拟，本仓库的测试状态统一放入 `local_debug/`。
