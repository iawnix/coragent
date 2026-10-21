# Slurm 接入

配置 `scheduler="slurm"`，handler 为 `["/usr/bin/python3", "/opt/coragent/skills/core/batch-schedulers/scripts/batch.py", "slurm"]`。通过 `CORAGENT_SBATCH`、`CORAGENT_SQUEUE`、`CORAGENT_SACCT`、`CORAGENT_SCANCEL` 配置原生命令路径。

`submission.queue` 选择 partition。CPU、内存、GPU 分别转换为 `--cpus-per-task`、`--mem`、`--gpus`。用 `squeue` 观察当前状态和等待原因，用 `sacct` 查询终态记账。设置 `AccountingStoreFlags=job_comment` 保留提交注释，恢复通过注释匹配完整请求身份。`COMPLETING` 仍处于清理过程，退出信号计入归一化退出码。

连接方式、存储和提交日志见[目标配置与恢复](targets.zh-CN.md)；查询、日志和取消检查见[原生命令](commands.zh-CN.md)。
