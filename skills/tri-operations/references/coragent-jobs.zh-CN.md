# 将 TRI 接入 CoRAgent Job

将随附的 [queue.py](../scripts/queue.py) 配置为通用外部目标的 handler。
提交主机需要 Python 3 和原生 `tri_sub`、`tri_stat`、`tri_del`。
脚本从 stdin 读取一个 JSON 请求，向 stdout 输出一个统一 JSON 响应，支持
`probe`、`submit`、`status`、`cancel` 和 `recover`。

CoRAgent 与 TRI 位于同一登录节点时，使用 `driver="external"` 和
`transport="local"`。`work_root` 指向与计算节点共享的持久目录，`handler`
指定已安装 Python 和本脚本的绝对路径。完整配置见[目标配置与协议](../../../docs/EXTERNAL_JOBS.zh-CN.md)。
研究计算继续通过 `job_start`、`job_status`、`job_reconcile` 和 `job_collect` 管理。

## Handler 环境

在目标的 `handler_environment` 中按需设置：

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

设置 `file_mode="shared"`，并将 `work_root` 指向共享工作区父目录，即可直接在
工作区任务目录执行；本机和 SSH 提交均支持。默认 `file_mode="staged"` 保留输入
传输与输出回收。共享检查由通用执行层负责，TRI 协议和处理器无需改变。
