# 原生命令与诊断

| 调度器 | 提交 | 查询 | 取消 |
| --- | --- | --- | --- |
| Qrun | CoRAgent `job_start` → `qrun handler` | `qrun resources`; `qrun jobs`; `qrun show 12` | `qrun cancel 12` |
| OpenPBS / PBS Pro | `qsub -q batch -l select=1:ncpus=4:mem=4096mb -l walltime=01:00:00 run.sh` | `qstat -x -f -F json JOB_ID` | `qdel JOB_ID` |
| Torque | `qsub -q batch -l nodes=1:ppn=4 -l mem=4096mb -l walltime=01:00:00 run.sh` | `qstat -x JOB_ID` | `qdel JOB_ID` |
| Slurm | `sbatch --partition=batch --cpus-per-task=4 --mem=4096 --time=60 run.sh` | `squeue -j JOB_ID`；`sacct -X -j JOB_ID -o JobID,State,ExitCode` | `scancel JOB_ID` |

脚本还会传入共享工作目录、独立的调度日志路径和稳定恢复身份。PBS 的 GPU
请求在 `select` 中增加 `ngpus`，Slurm 使用 `--gpus`。Torque 的 GPU 参数依赖站点，
使用前按该集群规则调整资源转换。显式 PBS `select` 替代单独的 CPU、内存和 GPU 字段。

PBS 的 `Q/W` 表示排队，`H/S` 表示挂起，`R/E` 表示运行或清理，`F/C` 结合退出码
确认完成。Slurm 的 `PENDING`、`RUNNING`、`COMPLETING` 与终态记账分别处理，
退出信号计入归一化退出码。查不到任务时状态为未知。

排队时检查 PBS 的 `comment` 和资源字段，或 Slurm 的 `%R`，比较请求时限、内存、
CPU 数和节点特性与分区限制。采用 Maui/Moab 的站点可用 `checkjob JOB_ID` 检查
资源可行性。失败时先看 `logs/scheduler.stdout`、`logs/scheduler.stderr`，再看
`logs/stdout.log`、`logs/stderr.log`。取消命令的响应确认请求已接收，最终记账确认
运行结束。CoRAgent 包装脚本另存超时证据，因此程序自行退出 124 仍归为程序失败。
