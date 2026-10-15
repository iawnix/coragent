# 执行插件接口

执行插件是运行时扩展，不是 Skill。Skill 只生成 Job 请求并选择已配置的
`execution_target`；插件负责 SSH、调度器命令、状态映射、取消和目标侧能力探测。

Core 提供以下稳定接口：

- `research_agent.jobs.RemoteScheduler`：调度器适配器接口；
- `research_agent.jobs.RemoteSSHPlatform`：SSH、staging、receipt、collect 和 Job 生命周期；
- `research_agent.jobs.PluginDescriptor`：插件注册描述；
- `tspi.execution_plugins`：Python entry point group。

一个独立插件包可以这样注册：

```toml
[project.entry-points."tspi.execution_plugins"]
pbs = "tspi_execution_pbs.plugin:descriptor"
```

`descriptor` 返回 `PluginDescriptor(scope="remote", driver="pbs", factory=...)`。
factory 接收一个 target 配置并返回 `RemoteSSHPlatform` 或实现了
`ExecutionPlatform` 的自定义平台。调度器实现只需要实现 `RemoteScheduler`，不应复制
输入 staging、receipt 写入或输出回收逻辑。

PBS、Slurm 和 tri 由独立发行包维护，Core 不再内置这些调度器实现。安装包分别为
`tspi-execution-pbs`（提供 `pbs` 和 `torque`）、`tspi-execution-slurm` 和
`tspi-execution-tri`。运行时只会发现已经安装的 entry point；配置选择了未安装的
driver 时会明确报告插件未安装。配置仍然只引用 target 名称：

```toml
[execution.targets.cluster_1w]
type = "remote"
driver = "pbs"
cluster_name = "1w"
ssh_host = "login.1w.example"
remote_root = "/scratch/coragent"
```
