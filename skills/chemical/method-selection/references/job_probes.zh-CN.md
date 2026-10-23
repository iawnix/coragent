# 计算环境合同

`job_start` 同时管理本地和远端目标的计算生命周期。本地或 SSH 传输连接选定的调度 handler。
使用 `job_probe` 配合 `execution_target: {"platform": "Com30", "scheduler_entry": "qrun"}`
做有界可用性检查，示例值替换为 Task 实际绑定的目标。

## 安装级策略

安装的主 `config.toml` 通过 `[execution]` 管理计算配置，`schema_version = 2`。
每个 `execution.platforms.<name>` 声明 `transport = "local"` 或 `"ssh"`、存储、
软件 `bindings`，以及 `schedulers` 下的调度入口。SSH 平台还声明 `ssh_host` 和可选
`ssh_config`。调度入口选择 `executor`、handler、提交默认值和资源上限，并可覆盖共享
软件绑定与存储。`CORAGENT_JOB_CONFIG` 指向生成的 `job.toml`，供执行工具读取，
不作为另一个独立维护的配置入口。

准备计算前，按[execution-platforms Skill](../../../core/execution-platforms/SKILL.zh-CN.md)
绑定 Task。`{platform, scheduler_entry}` 选择成为 Job 的 `execution_target`，
科学准备器继承该选择。请求资源须满足所选入口的上限。缺失的科学绑定由下述定向检查
报告；仅有传输可用性不证明科学方法就绪。

`job_probe` 检查平台可用性，不证明科学方法就绪。核实所选 backend 的命令、激活脚本和
Python 绑定可用[定向环境检查](runtime_environment.zh-CN.md)；需要时执行程序的有界 help/version 检查或 Skill 专用 doctor。
CF22D 的 [doctor.py](../../cf22d/scripts/doctor.py) 检查配置的 PySCF 环境和方法构造，
不证明其他程序就绪。当前没有内置 NEB 就绪探测或 workflow registry。
不要在研究 workspace 中安装科学依赖。

## 隔离

staged 存储下，远端目录由 Job 身份与工作区路径推导。上传 manifest 绑定文件与摘要，
请求还固定命令、环境、资源和预期输出。收集阶段把已声明输出下载到本地 workspace。
shared 存储使用配置的共享工作根目录及其目录身份检查，不复制执行目录。

## 控制生命周期

Submit 在调用配置的调度器前持久化生效前 staging 状态。一旦调度请求开始，传输失败的效果可能
不确定。即使之后队列/历史查询失败，也要保留任何已知 job ID 和持久化 submission record。

Cancel 同样区分已知未生效、已知取消和效果不确定。当任务从队列消失时，检查其回执与
声明的输出以确定实际情况。

Inspect 可以组合持久化回执、调度器状态、程序状态和已声明 Artifact 的有边界 tail。
Collection 遵循不可变 Artifact manifest，即使调度器历史不可用也能工作。

## 核验结果

- 在下一次控制动作前协调确认未知的 submit 或 cancel 结果。
- 新提交使用选定的平台配置；已有 Job 使用持久化的 route 与 intent。
- 分别核验所选平台和科学命令；仅有 SSH 连通性不足。
- 调度完成后检查程序终止状态和必需输出。
- 收集输出，在本地核验并解析后再记录研究记录。
