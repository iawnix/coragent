# 平台配置

唯一配置格式为 `execution.schema_version = 2`，包含 `default_platform` 和 `platforms`。
旧 `execution.targets` 配置会被拒绝。通过主安装器发布核对后的完整配置；登记平台不代表在每个提交端安装完整 CoRAgent。
在安装实例的 `config.toml` 中维护 `[execution]`；`CORAGENT_JOB_CONFIG` 指向生成的运行时配置，
不是另一份需要编辑的配置文件。

启用的平台定义 `transport`、`storage.work_root`、`default_scheduler` 和 `schedulers`。
SSH 平台还定义 `ssh_host`，使用已有 SSH 主机配置。未接入完成的平台可以设为 `enabled = false`，
但不能作为默认平台或接收作业。

平台的 `python`、`bindings`、`storage`、`submission`、`allowed_queues` 供入口共享。
入口的 `executor`、`handler`、`handler_environment` 和可选 `cluster_name` 描述队列。
入口可以覆盖软件、存储及提交默认值，但不能改变平台连接方式。覆盖软件时替换整条绑定；
资源默认值按字段合并，并受入口 `limits` 和队列权限限制。
limits 支持 cpus、memory_mb、gpus、walltime、max_in_flight。

CPU 数为逻辑 CPU 数，memory_mb 单位为 MiB。Python 绑定明确配置 manager=conda，
以及绝对路径 conda_executable、prefix、lock_ref。原生软件配置 command，可附带 activation_script
和 environment。软件未单独覆盖时，scratch 继承平台存储设置。

默认采用 staged，只有控制端、提交端和计算节点确实访问同一物理路径时才用 shared。
work_root 保存 Job 工作目录，scratch_root 保存临时数据。跨平台交接先收集声明输出为不可变 Artifact；
不能假定远端路径在本机存在。

handler 可达、软件可用和计算节点可执行是不同检查。软件检查命令为
`"$CORAGENT_PYTHON" -m research_agent.application.environment_check --config "$CORAGENT_JOB_CONFIG" --platform Com30 --scheduler-entry qrun --backend gaussian`。
登录端检查成功不代表计算节点可见软件或许可证可用。

改变默认值不迁移已提交 Job；相关配置改变后重新准备尚未提交的请求。
删除入口不能连带删除共享环境或未完成作业的数据。Qrun 可以归安装器管理，既有 PBS／Slurm／TRI 服务属于外部服务。
