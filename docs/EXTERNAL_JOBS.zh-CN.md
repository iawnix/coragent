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
`ssh_config`。此时 `handler` 与 `work_root` 是该主机上的路径。默认情况下，SSH 目标通过
rsync 暂存和收集文件；本机目标在控制端 Job 目录与 `work_root` 之间复制。
计算节点需要能以相同路径访问该目录，共享挂载由部署环境提供。
本机进程使用内置 process/systemd 驱动，批处理队列使用外部脚本。
Python 调度器插件加载机制已移除。

`handler_environment` 配置提交命令的环境，与计算程序环境分开。
凭据优先沿用已有受保护的服务/连接配置。Job 保存目标配置摘要；修改连接地址
或桥接程序后，原 Job 不会被悄悄指向新目标。恢复原目标配置后继续核对任务。

## 在共享工作区直接执行

文件处理方式与命令连接、调度系统独立。`file_mode` 默认是 `"staged"`，保持上述
复制流程。如果控制端、提交端和计算节点共享工作区文件系统，可以配置：

```toml
[execution.targets.compute]
driver = "external"
transport = "local"
file_mode = "shared"
work_root = "/home/iaw/DATA/coragent/workspaces"
handler = ["/usr/bin/python3", "/absolute/coragent/skills/tri-operations/scripts/queue.py"]
```

将目标合并到 `config.toml`，补齐实际连接环境和计算软件绑定。PBS、Torque、Slurm
及自定义处理器也使用相同选项。提交主机共享工作区时，同样可以用 `transport="ssh"`。
共享模式下 `work_root` 是允许执行的工作区父目录，不再创建另一份任务目录。
任务直接运行在工作区的 `runs/jobs/<job-id>/` 或请求指定的任务子目录中。

控制端会解析 `~/DATA` 等挂载别名；解析后的绝对任务路径必须在各节点一致可用，
不做路径映射。提交前通过临时文件双向读写检查提交端的共享存储。计算节点由调度器
分配后，执行入口先核对本任务的目录标记，才启动计算。除了调度器成功状态，控制端
还必须读到计算节点写入的启动和退出证据；证据缺失时保持未知状态，不会宣称成功。
共享检查失败会报错，不会自动改成复制模式。

普通 Job 接口仍将声明的输入保存为任务目录中的快照，共享模式省去的是向执行端的
第二次传输。直接调用 `JobSpec` 时，输入和 stdin 需先放在任务目录内。收集在原地
检查声明输出是否存在、大小和哈希是否有效，并拒绝控制文件输出与符号链接越界；
不会把文件复制到自己，也不会删除研究工作区。已有的后端 `scratch_root` 和
`{scratch}` 设置可让计算临时文件留在节点本地，需要保留的结果写回任务目录。
这个选项不会额外自动清理临时目录。

任务回执记录文件处理方式和执行目录。状态查询、取消、恢复与收集均需保留原目标
配置和共享目录。安装验收会在共享根目录下创建专属临时工作区，成功后删除该临时
工作区；失败或执行结果尚不明确时保留现场，供诊断和恢复。

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

## 逐作业资源

目标和后端配置中的资源是默认值，不是容量上限。执行器和脚本在准备时、`--` 分隔符之前
传入 `--cpus 12 --job-memory-mb 16384 --walltime 02:00:00`。可选的 `--gpus`、`--queue`、
`--queue-wait-seconds` 使用同一个合并入口，仍检查目标支持的字段和队列权限。
TRI 支持 CPU/内存/GPU，不接受 `queue` 或 PBS `select`。

每个字段按“目标默认值 → 后端默认值 → 明确的程序输入需求 → 本次 Job 申请”解析。
程序适配器在探测和提交之前检查矛盾，显式申请不会悄悄改写显式输入。
直接 Job 和验证器可传 `submission: {"resources": {"cpus": 12, "memory_mb": 16384}}`；
Python 的 `prepare`、`prepare_script` 使用相同的 `submission=` 参数。
直接 Job 不要同时在 `submission` 和 metadata 中指定资源。

Gaussian/PySCF 会留出至少 256 MiB 且不少于总内存 10% 的进程开销；这是默认预算，不能保证实际峰值。
显式 Gaussian 输入保持原样。路径和电子态 JSON 可以省略线程数及 Gaussian 内存，运行时读取已固定的
Job 资源。现有扫描、NEB 图像和交叉面计算是串行评估，图像数和曲面数不乘进 CPU 申请；不支持的并行参数
会被拒绝。xTB 和 CREST 的线程同样跟随申请。

最终资源进入工作身份、执行指纹和回执。修改资源必须重新准备；`job_start` 不允许覆盖请求文件或
prepared reference 的资源。软件环境、输入哈希和配置漂移校验继续保留。任意脚本会收到线程环境默认值，
但其内部并行度明确标为未验证；实际 CPU/内存限制由所选运行时或调度器负责。

TRI 负责节点容量、排队和分配。节点暂时忙碌以及默认 4 核均不代表硬件只能用 4 核。
12 线程共享内存任务需要某个合格节点单独满足容量，不能将多个节点的核数直接相加。
