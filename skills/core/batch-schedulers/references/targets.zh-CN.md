# 目标配置与恢复

```toml
[execution]
default_target = "batch"

[execution.targets.batch]
scheduler = "pbs"
location = "cluster"
driver = "external"
transport = "local"
work_root = "/shared/coragent/jobs"
handler = ["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "pbs"]
command_timeout_seconds = 180
allowed_queues = ["batch"]

[execution.targets.batch.submission]
queue = "batch"
queue_wait_seconds = 900

[execution.targets.batch.submission.resources]
cpus = 4
memory_mb = 4096
walltime = "01:00:00"
```

路径和队列名称按现场配置替换；调度器参数可选择 `slurm` 或 `torque`，同时将 `scheduler` 改为相同值。使用 SSH
时将 `transport` 改为 `ssh`、添加 `ssh_host`，并在该主机部署 Skill 脚本。
命令脚本运行在提交主机，调度器将已准备好的计算脚本分配给计算节点。接入所需
文件随 Skill 提供。

`handler_environment` 可通过 `CORAGENT_QSUB`、`CORAGENT_QSTAT`、
`CORAGENT_QDEL`，或 `CORAGENT_SBATCH`、`CORAGENT_SQUEUE`、
`CORAGENT_SACCT`、`CORAGENT_SCANCEL` 指定命令路径，每个值对应一个可执行文件。
计算软件绑定放在 `execution.targets.batch.bindings`。

PBS 模式读取 OpenPBS/PBS Pro 的 `qstat -x -f -F json`，包括保留的历史任务。
开启任务历史，并将保留时间设得长于控制端可能离线的时间。Torque 模式读取
`qstat -x` XML，恢复范围取决于该站点保留的记录。Slurm 需要 `squeue` 和 `sacct`，
并在记账中保留提交注释（`AccountingStoreFlags=job_comment`）。上线前用实际
提交账户检查这些查询。

脚本在提交前锁定并持久化提交意图，将完整请求身份写入 PBS 的
`CORAGENT_REQUEST_ID` 任务变量或 Slurm 注释。`recover` 只读已保存的调度器 ID，
或在当前/历史任务中匹配请求身份。已有意图未解决时，脚本停止重复提交。
历史记录过期后，查不到任务不能证明从未提交成功；创建替代 Job 前需要检查
调度历史。执行目录保留到输出收集和恢复结束。

通用协议见[外部任务接入](../../../../docs/EXTERNAL_JOBS.zh-CN.md)。

如需在工作区内直接执行，设置 `file_mode="shared"`，将 `work_root` 指向共享
工作区父目录。控制端、提交端和计算节点必须访问同一解析后的任务路径。三个
调度器及本机、SSH 提交均支持此模式，默认仍为 `staged`。共享检查见
[外部任务说明](../../../../docs/EXTERNAL_JOBS.zh-CN.md)。
