# 命名计算平台

[English](EXECUTION_PLATFORMS.md)

CoRAgent 将平台的连接、共享软件和存储，与平台内的调度入口分开配置。
唯一公共配置格式是 `execution.schema_version = 2`，选择格式是
`{"platform":"Com30","scheduler_entry":"qrun"}`。
`Com30/qrun` 只是安装参数和 Job 记录中派生的组合键，不是需要另配的 label。

## 配置与选择

[英文配套指南](EXECUTION_PLATFORMS.md#configuration)提供完整 TOML 示例：
FEDCluster 使用 local + TRI；Com30 使用 SSH `agent.com30` + Qrun；
1WCluster 登记 SSH `agent.1w`，在确认调度器与存储前保持 `enabled=false`。
示例中的 `/ABS` 路径须替换为核验后的路径，不能视为软件已经安装或服务已经部署。
示例 Qrun 入口使用默认 handler，供主安装器创建受管资源池。已有独立 Qrun 资源池时，
替换为其安装返回的完整 handler 参数数组（含状态目录）；主安装器的托管选项不会接管该池。

平台 ID 和别名不区分大小写，入口 ID 精确匹配。明确入口优先，否则用所选平台的默认入口；
按调度器类型筛选也仅限所选平台。平台级 `python`、`bindings`、`storage`、`submission`
和 `allowed_queues` 供各入口共享。入口覆盖一个软件绑定时替换整个绑定；存储和资源默认值
按字段合并，再检查队列权限与入口限额。入口不能覆盖平台连接或 SSH 主机。
CPU 表示逻辑 CPU，`memory_mb` 单位是 MiB。

Python 绑定明确 Conda 可执行程序、prefix 与 lock_ref；本地软件明确 command、
activation_script 和 environment。平台的 `storage.scratch_root` 提供软件临时目录默认值。
handler 凭据使用安装的凭据存储，平台查询不返回其值。

## 查询与执行

- `job_platforms`：列出平台、入口、软件绑定、实际生效的存储、资源默认值与限额，
  并说明软件／存储配置来自平台还是入口。配置存在不代表环境已验证。
- `job_resolve_target`：解析结构化选择并固定路由摘要。
- `job_resources`：查询所选 handler。Qrun 提供资源池总量、预留、空闲、观测用量与内存控制方式。
  其他现有 handler 未提供的容量返回 unknown，不当成零。
- 准备命令使用 `--platform Com30 --scheduler-entry qrun`。
  科学方法的 `--executor chemical.xtb` 选择计算配方，不选择调度器；进程变量仅使用 `environment`。
- `job_start` 统一检查选择、环境证据、输入摘要、资源与任务预算；准备后的执行字段不能覆盖。
  已提交 Job 的查询、取消、回收和核对使用记录中的原路由，不随新默认值改变。
- 普通 bash 始终在控制端执行，平台选择不会把普通 shell 自动改成 SSH。

普通研究任务不要求配置计算平台。task_begin 省略执行字段时，execution_target、execution_selection、
execution_policy 均保存为 null；工作区、研究记录、上下文管理与本地 bash 仍正常使用。
平台诊断也不会自动绑定 Task。

首次准备或直接提交计算前，先读取 task_read，再为未绑定 Task 调用 task_update：

```json
{
  "action": "bind_execution",
  "expected_revision": 1,
  "execution_target": {"platform": "Com30", "scheduler_entry": "qrun"}
}
```

修订号替换为当前 Task 的实际版本，选择仍受该任务真实用户来源约束；明确调度器指令通过
execution_intent 引用原文。省略目标时在这些约束下解析配置默认位置。缺少配置只会让当前绑定操作
失败，不改变 Task。已明确需要计算时，task_begin 也可直接提供执行字段完成绑定。
已有绑定不能再次用 bind_execution 替换；新要求用 refine 并引用新用户来源，误读原指令则用
correct_execution、原始明确指令和纠错原因。

执行计划不再设置固定项数上限，请求仍需符合传输消息大小限制；长依赖链使用迭代校验。
显式任务限额接受可精确表示的整数，不再额外限制并发参数最多为 1000；调度器与资源限额仍生效。
job_start.timeout_seconds 接受正的安全整数，不再限制最多 7 天。省略时不设置应用执行截止时间，
除非 submission.resources.walltime 提供该限制；两者同时提供时取较短时长，调度器自身策略仍生效。

一个 Task 可以包含多个独立放置的工作项。首次 task_update set_execution_plan 可以同时提供
execution 字段，原子保存未绑定任务的位置与计划；已绑定任务沿用原策略，已有计划固定其策略。
随后使用 select_execution_item 和 complete_execution_item 操作。
完整字段与使用步骤见 [执行计划](../skills/core/execution-platforms/references/plans.zh-CN.md)。
Job Manager 仍是实际作业状态的唯一来源；task_read 的 execution_progress 展示依赖、
原生执行状态、collecting 与 validating 阶段。

任务限制均为显式可选策略：max_in_flight、max_attempts、max_retries_per_work 省略或为 null，
分别表示不额外限制任务并发数、累计 Job 数、同一工作项重试数。max_attempts 保留旧字段名，
表示包含成功计算在内的累计 Job 数，不是失败重试额度。重试限制要求稳定 work_id，0 表示只允许首次执行。
旧任务已有的数值限制保留，不会自动清除。任务与入口限额仍在同一工作区事务锁内检查，
跨工作区的资源池由 Qrun／原调度器控制；unknown 或状态冲突的 Job 继续占名额。
并发占满返回 accepted:false、execution_task_capacity_reached 或 execution_entry_capacity_reached，
以及实际用量、上限和占位 Job ID，不创建或排入新 Job。继续独立工作；没有独立工作时，
用 task_update action=wait 等待本任务已有 Job，再恢复同一请求。未知／冲突状态先核实。
显式累计额度和重试额度分别返回 execution_task_job_limit_reached、execution_work_retry_limit_reached。
task_read.execution_usage 展示限制、累计用量和占位 Job。

通过 task_update action=set_execution_limits 提交 execution_limits、当前版本、原因和新的用户
source_submission_ids，可在保留计划的情况下调整限额；省略字段保持原值，null 清除限制。
审计记录保留调整前后数值与用户来源，原 Job、产物和位置不变。budget_exhausted 阻塞可随调整恢复，
其它阻塞和暂停状态不会被解除。确认 failed／timed_out／cancelled 的工作项可沿用 item/work_id，
使用新请求身份重试；相同计算仍须声明 repeat 的前驱、原因和预算。成功或执行结果不明的项不能这样重试，
已提交计划项的定义仍不可修改或删除。
对于已准备的文件／引用，repeat 自动派生稳定的尝试身份，保留原请求字节和 work_id；
重复同一声明复用该次 Job，再次重试则引用上一次 Job 作为前驱。

可选 automatic_placement=true 只允许在用户授权位置内，从工作项明确给定的 candidates 选择。
工作项还须声明 backend 和 CPU／内存需求。选择要求绑定存在、空闲资源已知且足够，排除暂停／过期
观测，并扣除本次计划已分配的资源。记录所选路由与选择依据，实际准备时继续核验软件。
目前 GPU 与非 Qrun 的可用容量未知，不能据此自动分配；显式选择 PBS／Torque／Slurm／TRI 仍可执行。
资源快照是估计，不能保证立即开跑，也不会代替调度器的真实预留。

依赖只有在上游 Job 成功、输出完成回收、当前科学验证 Result 引用了每个交接 Artifact 后才放行。
准备器自动将这些不可变内容暂存到 `inputs/artifacts/<artifact_id>/payload`，核对摘要，沿用现有
Artifact 来源记录。数据经控制端回收与转发；不同机器路径相同不代表共享存储。
rsync 使用摘要比较、部分传输文件和延迟发布；回收失败重试回收，不重跑已完成科学计算。
科学结论本身仍由领域方法验证。

## 安装、卸载与版本

通过主安装器发布完整配置（--config，或显式 --job-config 导入）。科学环境独立准备，
由平台／入口引用；现有 PBS、Torque、Slurm、TRI 服务不属于主安装器托管范围。
Qrun 的本机／SSH 安装与卸载统一使用主安装器的归属记录，详见 [Qrun 运维](QRUN.zh-CN.md)。

参数使用 `PLATFORM/ENTRY`，例如：

```sh
./install.sh --config /ABS/config.toml --manage-qrun Com30/qrun \
  --qrun-state-dir Com30/qrun=/home/agent/soft/Qrun/state \
  --qrun-cpus Com30/qrun=112 --qrun-memory-mb Com30/qrun=377221 \
  --qrun-runtime Com30/qrun=portable
```

此命令用于安装器托管的资源池，不用于接管已独立安装的自定义 handler。
卸载仅移除所属服务／环境，不停止外部调度器，不删除研究工作目录。
Qrun 有未结束作业时拒绝移除，除非明确要求取消。多个入口可引用同一个环境 prefix；
删除配置入口本身不会卸载该环境。

旧的平铺 targets、process／systemd 执行器被拒绝；没有自动迁移、旧选择别名或第二份可编辑目标表。
持久化版本为 `coragent-user-task/6`、`job_intent/4`。部署前应先用旧版本处理完在途工作，
再同步切换配置和运行时；新版本记录原路由不代表转换旧回执。

新增 [execution-platforms skill](../skills/core/execution-platforms/SKILL.zh-CN.md) 负责选择、环境、
存储与交接；[batch-schedulers](../skills/core/batch-schedulers/SKILL.zh-CN.md) 负责调度器操作；
TRI 部署维护放在 [普通文档](TRI_OPERATIONS.zh-CN.md)。
CentOS 7 的 Qrun portable 仍使用 CPU affinity 与 RSS 采样，不是 cgroup 内核硬限制，
生命周期也不跟随 PBS。本次源码重构不会自动登记或重新部署生产集群。
