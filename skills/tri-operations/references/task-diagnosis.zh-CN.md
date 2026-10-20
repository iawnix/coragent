# 任务诊断与恢复

## 定位同一个任务

CoRAgent Job 从回执的 `scheduler_id` 取得 TRI 数字任务 ID，并在该执行目标上运行诊断命令。直接提交的任务使用 `tri_sub --json` 返回的 ID。用 `tri_stat --json "$TRI_TASK_ID"` 查看状态、节点、attempt、租约、退出码、错误和日志路径，对照 `tri_node --json` 及同一时段的服务日志。

## 按现象排查

| 现象 | 检查与处理 |
| --- | --- |
| CLI 无法连接 | 检查 socket 路径、所属用户和服务端单元。存在的陈旧 socket 会先于 TCP 被尝试，调整 socket 前核实对应服务。TCP 检查地址、连通性和令牌配置。 |
| 协议/Hello 不匹配 | 对比服务端、CLI、客户端构建身份，部署兼容的一组程序后重新查询。 |
| `wait` | 将请求的 CPU、内存、GPU、节点与在线节点容量及已分配资源比较，检查依赖任务 ID 和完成状态，按原因修正请求或恢复所需节点。 |
| `blocked` | 检查 `--after` 依赖，前置任务失败、取消或失联会阻塞后续任务。处理前置任务后检查后续记录，再安排替代工作。 |
| `run` 但输出很少 | 检查分配节点、attempt、任务单元和程序活动，核对 stdout/stderr 路径及程序缓冲。日志安静本身不足以定位故障。 |
| `fail` | 查看退出码、TRI 错误和 stderr；从任务单元日志检查启动、权限、程序路径、cgroup/OOM 错误，再检查应用自身日志。 |
| `timed_out` | 对比运行时间与原生超时限制，检查部分结果和 checkpoint，选择合适的续算方式或时限。 |
| `lost` | 检查节点连通性、客户端心跳/租约和实际任务单元。恢复客户端连接、核对 attempt 后再决定是否重算。 |
| `done` 但文件缺失 | 对比 `--chdir`、输出路径、共享挂载和 scratch 回传。`tri_log` 在 CLI 所在主机打开返回路径，因此该主机需要能读取文件。 |

## 资源与任务单元

计算节点上的任务单元名为 `tri-task-<id>-<attempt>`。使用返回的 ID/attempt，并在计算服务账户下执行：

```bash
systemctl --user status "$TRI_TASK_UNIT" --no-pager
journalctl --user -u "$TRI_TASK_UNIT" -n 100 --no-pager
```

CPU 分配使用 `AllowedCPUs`，GPU 使用可见性变量和设备规则。`--mem` 设置 `MemoryMax` 并关闭任务 swap。内存限制失败时，对比实际峰值、申请量和节点容量。`--timeout` 使用 `RuntimeMaxSec`，排查时与应用自身返回非零退出码区分。

节点客户端启动或重连时会核对任务单元，可以接管匹配的已有 attempt。当 `--max-attempts` 允许时，租约到期可能触发下一次执行。默认是一次；任务的输出和副作用支持重复执行时，再选择更大的次数。

## 提交身份、取消与日志

可重试提交使用在安装/工作流内唯一的 `--request-id`，需要按工作流查找时还可设置 `--external-id`。相同标识与相同任务规格返回已有任务；改变规格时使用新身份。按已知外部身份恢复查询：

```bash
tri_stat --json --external-id "$TRI_EXTERNAL_ID"
```

CoRAgent 管理的任务通过原 Job 执行 `job_reconcile`、`job_cancel` 和 `job_collect`。用户要求取消直接管理的 TRI 任务时：

```bash
tri_del --json "$TRI_TASK_ID"
tri_stat --json "$TRI_TASK_ID"
```

取消记录可能先于运行进程退出出现，客户端通过心跳收到取消信息。核实节点任务单元停止、资源分配释放。节点不可达时，说明取消已记录、执行是否停止仍待确认。

`tri_log ID` 读取 stdout，`tri_log --stderr ID` 读取 stderr，`--follow` 交互跟随输出。未分别设置输出选项时，两者合并到任务目录下的 `tri-<id>.out`。输出/错误路径中的 `%j` 展开为任务 ID，相对路径按 `--chdir` 解析。

## Scratch 与历史保留

任务获得节点本地的 `TRI_SCRATCH`，`--scratch-cwd` 会让命令从该目录启动，原始目录保存在 `TRI_JOB_CWD`。将输入和可执行脚本暂存到节点可读位置，在任务退出前把最终输出/checkpoint 复制回持久任务目录。客户端会尽力清理 scratch，检查残留目录前先定位任务 attempt 和最终输出。

用户要求维护历史时，选择保留期限，先收集仍需使用的 Job 输出与回执。`tri_clean --json --older-than SECONDS` 删除较旧的终态记录，默认期限为 30 天。清理同时删除幂等回执，此后重试已清理请求可能生成新任务。保留窗口应覆盖工作流恢复和重试需求；`--all` 用于明确选定的全部终态历史删除。

取消时核对 `cancel_confirmed` 和 `completion_reason`。即使已有 `finished_at` 且租约为空，租约到期仍不能证明进程停止；等待完成确认期间，资源仍应视为占用。
