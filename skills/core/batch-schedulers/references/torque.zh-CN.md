# Torque 接入

配置 `executor="torque"`，handler 为 `["/usr/bin/python3", "/opt/coragent/current/agent/skills/core/batch-schedulers/scripts/batch.py", "torque"]`。原生命令为 `qsub`、`qstat`、`qdel`，通过 `CORAGENT_QSUB`、`CORAGENT_QSTAT`、`CORAGENT_QDEL` 覆盖路径。

CPU 请求转换为 `nodes=1:ppn=N`，内存为 `mem=Mmb`。GPU 语法依赖站点，申请前先按本站规则调整并测试资源转换。handler 读取 `qstat -x` XML，恢复范围取决于安装保留的记录，匹配 `CORAGENT_REQUEST_ID`。Maui/Moab 站点可用 `checkjob JOB_ID` 诊断资源可行性；记录消失仍为未知状态。

连接方式、存储和提交日志见[目标配置与恢复](targets.zh-CN.md)；查询、日志和取消检查见[原生命令](commands.zh-CN.md)。
