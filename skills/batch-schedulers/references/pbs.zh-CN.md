# PBS / OpenPBS / PBS Pro 接入

配置 `scheduler="pbs"`，handler 为 `["/usr/bin/python3", "/opt/coragent/skills/batch-schedulers/scripts/batch.py", "pbs"]`。原生命令不在 PATH 时，通过 `CORAGENT_QSUB`、`CORAGENT_QSTAT`、`CORAGENT_QDEL` 指定路径。

CPU/内存转换为 `select=1:ncpus=N:mem=Mmb`，GPU 添加 `ngpus`；显式 `resources.select` 替代单独 CPU/内存/GPU 字段。通过 `qstat -x -f -F json` 查询保留历史，历史保留期应覆盖控制端离线时长。恢复匹配任务变量中的 `CORAGENT_REQUEST_ID`。`Q/W` 为排队，`H/S` 为挂起，`R/E` 为运行或清理，`F/C` 结合退出码确认终态。

连接方式、存储和提交日志见[目标配置与恢复](targets.zh-CN.md)；查询、日志和取消检查见[原生命令](commands.zh-CN.md)。
