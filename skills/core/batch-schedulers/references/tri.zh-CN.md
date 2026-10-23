# 将 TRI 接入 CoRAgent Job

## 内容

- [Handler 环境](#handler-环境)
- [资源与状态处理](#资源与状态处理)
- [提交与诊断](#提交与诊断)
- [按计算节点和后端验收](#按计算节点和后端验收)

将随附的 [tri.py](../scripts/tri.py) 配置为 `executor="tri"` 调度入口的 handler。
提交主机需要 Python 3 和原生 `tri_sub`、`tri_stat`、`tri_del`。
脚本从 stdin 读取一个 JSON 请求，向 stdout 输出一个统一 JSON 响应，支持
`probe`、`submit`、`status`、`cancel` 和 `recover`。

CoRAgent 与 TRI 位于同一登录节点时，平台使用 `transport="local"`，
`storage.work_root` 指向与计算节点共享的持久目录。调度入口的 `handler`
指定提交端 Python 和本脚本的安装绝对路径。完整配置见[目标配置与协议](../../../../docs/EXTERNAL_JOBS.zh-CN.md)。
研究计算继续通过 `job_start`、`job_status`、`job_reconcile` 和 `job_collect` 管理。

原生任务状态、取消确认和日志检查见[TRI 任务诊断](tri-diagnosis.zh-CN.md)；服务端与节点部署见[TRI 运维](../../../../docs/TRI_OPERATIONS.zh-CN.md)。

## Handler 环境

在调度入口的 `handler_environment` 中按需设置：

| 变量 | 用途 |
| --- | --- |
| `TRI_SOCKET` | 登录主机上的队列 socket |
| `TRI_SERVER_ADDR` | 使用 TCP 而非本机 socket 时的服务地址 |
| `TRI_AUTH_TOKEN` | TCP 认证，沿用安装环境受保护的凭据配置 |
| `CORAGENT_TRI_SUB`、`CORAGENT_TRI_STAT`、`CORAGENT_TRI_DEL` | 原生命令不在 PATH 时指定绝对路径 |
| `CORAGENT_TRI_NODE` | 可选的固定计算节点名，未指定时由 TRI 选择 |

通过 SSH 提交时，在登录主机安装同一个 handler，并配置该主机上的路径和
连接环境。Job 协议及辅助脚本保持一致。

## 资源与状态处理

`resources.cpus`、`memory_mb`、`gpus` 分别转换为 `--cpu`、`--mem`、`--gpu`，
Job 的有效运行时限转换为 `--timeout`。TRI 按节点和资源分配任务，无需 PBS/Slurm
式的队列选择。运行脚本在共享工作目录中执行，计算进程日志写入
`logs/stdout.log` 和 `logs/stderr.log`，TRI 自身的任务日志写入
`logs/scheduler.stdout` 和 `logs/scheduler.stderr`。

提交将 Job 的稳定请求身份同时作为 `--request-id` 和 `--external-id`。
恢复使用 `tri_stat --external-id` 查找原任务。脚本将 `wait` 转换为排队，
`run` 转换为运行，`lost` 转换为未知。运行中的取消请求保持待确认，直到 TRI
报告完成；仅因租约到期关闭、尚无进程退出证据的取消仍保持未知，继续核对原 attempt。

检查 handler 的连接而不提交计算时，将 `TRI_JOB_HANDLER` 设置为已安装脚本路径，
在配置好的环境中运行：

```bash
python3 "$TRI_JOB_HANDLER" <<'JSON'
{"schema_version":"coragent-external-job/1","action":"probe"}
JSON
```

设置 `storage.file_mode="shared"`，并将 `storage.work_root` 指向共享工作区父目录，即可直接在
工作区任务目录执行；本机和 SSH 提交均支持。默认 `storage.file_mode="staged"` 保留输入
传输与输出回收。共享检查由通用执行层负责，TRI 协议和处理器无需改变。

## 提交与诊断

TRI 成功提交回执必须包含 `driver="external"` 和非空 `scheduler_id`；本机 handler 成功运行不证明任务进入了 TRI 队列。

原生 `invalid_request` 明确拒绝会保存为失败 Job，标记
`action_outcome=not_submitted`。响应丢失、`request_id_reused` 和
`external_id_conflict` 仍表示结果不确定，应先核对原 Job，再考虑替代计算。
保留原生错误码和可重试标记；可重试标记本身不代表可以再次提交。

提交和恢复响应必须匹配稳定外部身份；查询和取消还要核对原数字 ID。
身份不符保持未知，并阻止取消。TRI 当前仅支持按数字 ID 取消，因此核对与取消
无法组成原子操作；操作进行时不要重建或替换队列。

诊断分别显示实际观察到的节点、申请的 CPU/内存/GPU、有效内存和 swap 上限，以及
分配的 CPU/GPU 集合。申请量不能当成实际分配证据。`resource_failure` 区分
`memory_limit` 和 `resource_enforcement` 失败，普通命令失败时为空。固定
`CORAGENT_TRI_NODE` 的目标还会给出 `requested_node` 和 `node_match`，明确实际分配
是否一致。排队或挂起时，`wait_seconds` 表示距 TRI 的 `created_at` 的时间；时间戳
缺失仍为未知。该值接入已有 `queue_wait_seconds` Monitor 阈值，每个 Job 仅产生一次
排队超时事件，普通排队/运行变化不唤醒代理。运行中任务取消需完成证据及
`cancel_confirmed=true` 才视为终态；`completion_reason=lease_expired` 不能证明进程已停止。

## 按计算节点和后端验收

登录主机环境探测通过，或一个自由调度的 Job 成功，不等于所有计算节点可用。
为配置了此 TRI handler 的目标显式运行验收入口。将 `CORAGENT_PYTHON` 设为
已安装 CoRAgent 运行环境的 Python，`CORAGENT_PACKAGE_ROOT` 设为软件包目录，
`TRI_ACCEPTANCE_DIR` 选择尚不存在的私有目录（仓库测试必须位于 `local_debug/`）：

```bash
"$CORAGENT_PYTHON" "$CORAGENT_PACKAGE_ROOT/packaging/coragent_packaging/installer/verify_tri_nodes.py" \
  --config "$HOME/.config/coragent/config.toml" \
  --package-root "$CORAGENT_PACKAGE_ROOT" --directory "$TRI_ACCEPTANCE_DIR" \
  --platform compute --scheduler-entry main --nodes '["fed1","fed2"]' --timeout 180
```

将目标和节点名替换为部署的准确名称。脚本通过私有配置副本设置
`CORAGENT_TRI_NODE`，提交有时间限制的验收 Job，不改动现用配置。
对带有软件包验收检查的后端，核验结果，并要求实际节点与指定节点相同。
`report.json` 逐节点记录已验证/未验证后端、实际节点和资源诊断。
未选择的节点仍未验证；缺少检查、检查失败、节点缺失或不匹配，均不能得到完整成功退出码。
这些检查证明环境就绪，不证明科学结果准确或计算性能达标。

成功后删除共享验收工作区和私有配置副本；失败时保留核对任务所需的工作区与配置。
取消操作有确认等待时限，尚未确认则保留证据。配置可能含连接凭据，相关文件应保持私有。
核心安装器不会自动执行这项集群验收。
