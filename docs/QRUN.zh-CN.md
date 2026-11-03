# Qrun：本机与 SSH 作业队列

[English](QRUN.md)

Qrun（Queue + Run）是单机 CPU／内存 FIFO 队列。
CoRAgent 管科学 Job、输入传输和结果回收；Qrun 管排队、资源预留和执行记录。
本机和 SSH 远端使用同一程序，需要 Python 3.11+。现代 Linux 使用用户级 systemd
和 cgroup v2；CentOS 7 等旧系统可使用无需 root 的 portable 运行方式。

## 执行目标配置

`transport = "local" / "ssh"` 与 `executor` 独立选择。executor 支持
`qrun`、`pbs`、`torque`、`slurm`、`tri`、`external`。本机和远端裸机统一使用 Qrun，
其他执行器需要对应 handler，支持多个本机目标。
旧的 `driver`、`supervisor`、`scheduler`、`type` 配置字段及直接 process/systemd
执行器已经移除。旧配置需改写为 `transport + executor`，旧直接执行回执不会交由
Qrun 接管。systemd 作为 Qrun 内部的进程管理机制。

完整配置见 [job.qrun.example.toml](../config/job.qrun.example.toml)。handler、软件绑定、
工作目录均指执行主机上的路径。默认 handler 是 `["qrun", "handler"]`；主安装器托管
队列时会自动改为稳定的绝对路径数组。独立管理时，需要 qrun 命令位于非交互 PATH 中。
SSH 上传／回收模式需要两端都有 rsync；共享模式沿用现有文件系统验证。
每个 Job 必须明确请求 CPU 和内存，可以由目标／软件默认配置提供。

## 通过主安装器管理

先在主配置 `config.toml` 声明平台和调度入口，可参考上述示例中的 execution 配置。
没有执行配置时，安装器不创建资源池。主安装器管理明确配置且使用默认 handler 的
本机 Qrun 入口，多个本机入口共用一个资源池。
默认预算为当前进程可用 CPU 数减一（至少一个）和主机物理内存的 75%，可明确调整：

```sh
./install.sh --config /ABS/config.toml \
  --qrun-cpus local/qrun=8 --qrun-memory-mb local/qrun=16384
```

上例假定 `local` 平台已配置 `qrun` 入口。为 `com30` 平台声明 `transport = "ssh"`、
`ssh_host = "agent.com30"`，并为其 `qrun` 入口声明 `executor = "qrun"` 和默认 handler 后，
可以显式托管远端队列：

```sh
./install.sh --config /ABS/config.toml --manage-qrun com30/qrun \
  --qrun-state-dir com30/qrun=/home/USER/.local/state/coragent/qrun \
  --qrun-cpus com30/qrun=32 --qrun-memory-mb com30/qrun=65536
```

替换 USER。远端首次托管必须提供状态目录、CPU 和内存；SSH 使用已有配置和非交互认证。
只向执行主机发送独立 Qrun 程序与资源池配置，不复制模型配置或凭据。本机使用系统
`/usr/bin/python3`，远端使用 `python3`，均需 3.11+，不依赖 Agent 的可替换 Conda 环境。
systemd 方式需事先启用 lingering：`loginctl enable-linger USER`。
无 cgroup v2 时，`auto` 自动选择 portable；也可用 `--qrun-runtime com30/qrun=portable`
明确选择。已有资源池固定其运行方式，不能在升级时混用两种进程管理机制。

安装计划及 `--dry-run` 会列出目标、主机、预算和状态目录。`--service-scope none`
仅写服务配置，不启动队列；需要执行验收作业时应使用正常服务模式。
自定义 handler 不会被自动接管；`--without-managed-qrun` 使用独立管理的队列。
不同 SSH 别名不会自动判定为同一主机，应使用同一规范别名，以避免重复分配资源。
已有资源池保持 transport、SSH 主机和状态目录不变时，可在升级中新增、修改或移除
`ssh_config`，后续维护与卸载使用更新后的连接设置。共享同一池的入口须使用相同的
`ssh_config`。

升级由同一安装器完成，要求队列已排空，保留账本与稳定 handler 路径，可通过以上参数
显式调整容量；未传容量参数时保留在线调整后的预算。安装失败时会尝试恢复原服务与配置；无法联系远端时保留归属记录供重试恢复。
进入应用服务启动阶段后的失败保留新版本，重新运行安装器向前修复。

主卸载器会移除该安装托管的本机及 SSH 队列服务，默认保留历史与计算文件。
存在未完成作业时拒绝卸载；明确取消后再卸载可用：

```sh
./uninstall.sh --cancel-qrun-jobs
./uninstall.sh --purge-qrun-state
```

`--purge-qrun-state` 删除所属队列的状态和历史，不删除计算工作目录；
`--purge-all` 包含队列状态清理，但不会隐含取消未完成作业。
独立安装的队列不属于主卸载器的管理范围。

## CentOS 7 / portable 运行方式

portable 是 Qrun 内部的运行方式，执行器仍为 `qrun`，与 `transport = local/ssh`
独立。它使用 Linux 子进程收养机制（subreaper）、进程身份记录和取消标记管理作业，
不要求 systemd 用户服务或可写 cgroup。后台队列脱离 SSH 会话；安装器为当前用户
添加带归属标记的 crontab 条目：开机启动，以及每分钟检查并启动已退出的队列。
用户 crontab 和系统 cron 服务必须可用；卸载只移除该资源池的条目。

两种运行方式都提供持久化 FIFO、CPU／内存预算、超时、取消、结果记录和队列恢复。
portable 对并发作业分配不重叠的 CPU 核心集合，子进程继承 CPU affinity；
内存以整个进程树的 RSS 定期采样，超过预算后终止。**RSS 采样不是内核内存硬限制**：
用量可能在采样之间超限，共享页也可能重复计数，不适合作为不可信作业的隔离边界。

正常完成、取消和超时都会收养、终止并回收脱离进程组或双重 fork 的后代，再写入完成
记录。队列重启不重跑已有作业；若作业监督进程被外部 `SIGKILL` 强制杀死，无法确认
后代已退出时会保持 `unknown` 并保留预算，需要人工处理，不宣称与 cgroup 隔离等价。

独立部署示例：

```sh
python3 -B /home/agent/soft/Qrun/qrun.py \
  --state-dir /home/agent/soft/Qrun/state \
  install --runtime portable --cpus 112 --memory-mb 377221 \
  --work-root /home/agent/soft/Qrun/jobs
```

主安装器使用 `--qrun-runtime PLATFORM/ENTRY=portable`，其安装、升级、恢复和卸载流程与
systemd 方式相同。查看状态使用安装返回的 program 和 `--state-dir`，执行
`service status`。`service stop` 只是临时停止守护进程，已启用的 cron 会在下一分钟重新启动；
暂停派发应使用 `pause`，恢复使用 `resume`；
持久停用请走卸载流程。`probe` 响应会报告实际 runtime 和 memory_enforcement。

## systemd 独立安装（可选）

wheel 包提供 qrun 命令，也可以只复制 `backend/src/research_agent/jobs/qrun.py`
到执行主机。该文件只使用标准库，无需完整 Agent 或模型配置。分别在执行主机运行：

```sh
loginctl enable-linger USER
python3 -B /absolute/path/qrun.py \
  --state-dir /home/USER/.local/state/coragent/qrun \
  install --runtime systemd --cpus 32 --memory-mb 65536 \
  --work-root /home/USER/DATA/qrun-jobs
```

替换 USER、路径和预算。安装检查用户管理器及 lingering（保证退出登录后继续运行），
创建私有资源池，将程序复制到内容版本固定的路径，安装、启用并启动用户服务。
返回的 JSON 包含 unit、unit_path、program，以及填入 CoRAgent 的完整 handler 数组。
`--no-start` 只写文件；`init` 只创建资源池，`serve` 前台运行队列，`unit` 输出服务定义。

每个用户、每台执行主机使用一个规范资源池。多个工作区、SSH 别名应连接同一池。
独立资源池不能重复声明同一份预算。Qrun 不会替其他用户或软件预留整台机器。
状态应保存在持久化本地文件系统，并与允许的工作根目录分离。

## 排队与恢复

- CPU 和内存同时足够才启动；超过总容量的请求直接失败。严格 FIFO，不回填、不抢占，
  不支持 GPU、命名队列或 PBS select。CPU quota 限制时间，不代表独占绑核。
- 队列不依赖 SSH 或 CoRAgent 持续在线。停止队列服务不停止独立计算服务，重启先恢复。
- 启动前通过 SQLite 提交身份与预留；重复请求返回原编号。响应丢失不自动重跑。
- 取消意图持久化并阻止迟到的启动。已受理不等于已终止；取消前已保存的完成结果保留。
- 计算及 cgroup 后代均终止后才释放资源。证据缺失时保持 unknown 并保留资源。
  主脚本退出后仍有后代存活，也会停止整个 cgroup。
- 结果不依赖服务一直存在。主机重启后保留已有结果，否则将活动作业标记失败，不自动重跑。
- queue_wait_seconds 仍用于 CoRAgent 等待观察，不自动使作业过期。
  第一版保留历史，不做多节点分配。

## 资源、作业、日志与控制

以下命令使用已安装的 `qrun` 包装器；没有包装器时，使用安装返回的 program 并加上
`--state-dir /实际状态目录`。本机与 SSH 远端命令完全相同：

```sh
qrun status                           # 队列总览、服务在线情况
qrun resources                        # 总预算、预留、可派发、主机实际可用内存
qrun jobs                             # 未完成作业，按 FIFO 顺序
qrun list                             # 兼容旧调用的完整账本 JSON 导出
qrun list --json                      # 显式 JSON 导出，与 list 相同
qrun jobs --all --limit 20             # 包括历史，最新优先
qrun jobs --state failed               # 可重复 --state 筛选
qrun show 4                           # 数字作业编号
qrun logs 4                           # 最近 16 KiB 标准输出
qrun logs 4 --stream stderr --follow   # 跟随错误输出，作业结束后退出
qrun watch                            # 每两秒刷新资源和作业
qrun pause                            # 持久暂停派发，已有作业继续运行
qrun resume
qrun config --cpus 112 --memory-mb 377221
qrun cancel 4
```

在 com30 上：

```sh
ssh agent.com30 /home/agent/soft/Qrun/qrun resources
ssh agent.com30 /home/agent/soft/Qrun/qrun jobs --all
ssh agent.com30 /home/agent/soft/Qrun/qrun show 4
```

作业编号为池内持久递增的数字，例如 `4`；提交／恢复回执中的 `scheduler_id` 为同一编号的字符串。跨主机使用时同时保留目标／资源池身份。
这些命令支持 `--json`，查询响应标记 `qrun-view/1`；`jobs` 支持 `--limit`（1–100）
与 `--offset` 分页。`watch --count N` 可限定刷新次数，Ctrl-C 结束显示。
`list` 保留旧的完整账本 JSON 数组、字段和升序，终端和管道行为一致，不破坏旧脚本；
`list --json` 是显式的等价写法。该导出不包含在线／新鲜度标记。
人工查看历史使用 `jobs --all --limit 20`，自动化查询使用同一命令加 `--json`。

交互终端使用颜色强调：成功为绿色，运行／启动为青色，排队／暂停／取消和等待原因为黄色，
失败／超时／未知、离线提示及超出预算为红色。状态文字始终保留，颜色只是辅助。
重定向或管道输出、设置 `NO_COLOR`（包括空值）、`TERM=dumb` 时不着色；JSON 输出不含颜色。
例如 `NO_COLOR=1 qrun jobs`。`qrun --help` 按查询、控制、安装维护分组；内部协议与执行入口
仍可由安装器和守护进程调用，但不列入日常帮助。`qrun --help-all` 提供自动化与完整入口说明。

资源显示区分三种含义：

- **调度预算**：配置的 CPU／内存总额；预留涵盖 starting、running、stopping、unknown。
  可派发资源等于预算减预留，不会因为作业暂时没用满就把这部分重复派发。
- **作业实际用量**：采样 CPU 核当量、内存、累计 CPU 秒、采样内存峰值和采样时间。
  portable 使用进程树 RSS，systemd 使用 cgroup v2。缺失或超过三秒的活动作业采样标记
  stale，不冒充零用量。历史保留最后采样；旧版本作业可能没有用量与日志。
- **主机资源**：逻辑 CPU、进程允许使用的 CPU 数、主机 CPU 忙碌比例、MemAvailable
  和负载。它包含 Qrun 外的程序；主机空闲不等于 Qrun 可派发，Qrun 预算也不保证外部
  程序不会争用内存。portable 的 RSS 采样峰值不是精确峰值，也不是内核硬限制。

`show` 给出请求资源、工作目录、运行／等待时长、退出码、错误、取消／清理状态及排队原因：
paused、资源不足、前序 FIFO 作业阻塞、超过缩容后预算、等待下次派发。
严格 FIFO 下，超过新容量的队首会阻塞后续作业；可提高预算或明确取消该作业。

在线缩容不会终止已有作业；超出新预算的部分显示为 overcommitted，等待资源释放后再派发。
portable CPU 预算上限为当前允许使用的逻辑 CPU 数，内存预算不能超过主机物理内存。
`pause` 在服务重启后保留；查询、取消、回收和正在运行的作业均继续。
**只有代码升级仍要求排空队列，日常增减资源预算不要求排空。**

守护进程不可达时，查询读取历史账本并明确标记 OFFLINE/stale；不把历史状态当作实时运行证据，
也不允许离线修改队列。日志默认读 CoRAgent 作业的 logs/stdout.log 或 stderr.log，
直接脚本读 Qrun 捕获的输出；只允许固定日志文件，拒绝符号链接，单次最多读取 64 KiB。
日志保留在磁盘，不自动轮转或清理；长期输出较多的作业需自行规划磁盘容量。
CoRAgent 的 `job_probe` 现在返回同一队列总览，普通 Job 状态 diagnostics 包含用量与排队原因。
缺失的单作业采样使用 `available=false` 和空测量值。汇总的 `job_usage.cpu_cores`、`memory_mb`
兼容保留原含义：只对新鲜采样求和，可能只是部分作业。新增 `complete`、`total_cpu_cores`、
`total_memory_mb`：存在缺失／过期活动采样或服务离线时，总量为 null；在线且无活动作业时为完整的零。

## AI 与程序接口契约

人使用表格，AI／程序显式使用 `--json`。输出格式不随终端／管道改变，只有颜色自适应；
操作命令不询问交互确认。`--help`、`--help-all` 始终输出文本，即使同时提供 `--json`。

### JSON 格式和退出码

`status`、`resources`、`jobs`、`show`、`logs`、`watch`、`pause`、`resume`、`config`、
`cancel` 支持 `--json`。成功结果保留所有原有顶层字段，新增 `cli_version: "qrun-cli/1"`、
`ok: true`、`command`（调用的命令名）。失败同样包含版本、`ok: false`、`command` 和
`error`，其中有 `code`、`message`、`retryable`、`action_outcome`、`recovery`。
参数解析失败时 `command` 为 null。消费者必须容忍新增字段。CLI 版本、查询版本
`view_version: "qrun-view/1"`、handler 的 `schema_version` 各自描述不同边界。

退出码：0 表示成功响应（包括明确标记为过期的离线读取），1 表示操作失败，2 表示参数解析
失败，130 表示 JSON 命令被中断。还要检查 JSON 字段，不能只看退出码。
stdout 只放 JSON 结果；帮助文本和兼容的 `list` 数组是 CLI 对象格式的例外。
`watch --json`、`logs --follow --json` 输出逐条立即刷新的 **JSON Lines**；后续发生错误时
追加一条错误记录，以非零码退出。有限观察用 `watch --count 1 --json`，其中 overview 和 jobs
是分别读取的快照，不保证同一时刻。

```sh
qrun jobs --all --limit 20 --offset 0 --json
qrun show 4 --json
qrun logs 4 --stream stderr --bytes 4096 --json
qrun watch --count 1 --json
qrun cancel 4 --json
```

例如 `qrun jobs --limit invalid --json` 返回退出码 2 和以下结构：

```json
{"cli_version":"qrun-cli/1","ok":false,"command":null,"error":{"code":"invalid_arguments","message":"argument --limit: invalid int value: 'invalid'","retryable":false,"action_outcome":"not_submitted","recovery":"Check qrun COMMAND --help and correct the arguments."}}
```

| 错误码 | 含义与处理 |
| --- | --- |
| `invalid_arguments` | 按子命令帮助修正参数。 |
| `job_not_found` | 核对执行主机、资源池和数字编号。 |
| `state_unavailable` | 无法读取本地配置／账本，检查安装、目录与权限。 |
| `qrun_unavailable` | 守护进程不可达或回执丢失，修改操作可能已生效。 |
| `response_too_large` | 缩小作业页或日志片段。 |
| `qrun_error` | 其它守护进程／运行时拒绝或错误，查看说明及当前状态。 |
| `interrupted` | 客户端被中断，进行中的修改可能已经生效。 |

`retryable` 是诊断信息，**不表示可以直接重复修改操作**。保留守护进程的 `action_outcome`；
`unknown` 不等于明确拒绝。CLI 参数解析错误的 `not_submitted` 表示尚未派发请求。
控制操作丢失回执后，先查询 `config`、`status` 或 `show` 核对是否已生效；程序不会自动重试。
提交任务则遵循下述身份／恢复流程。

### 观测、单位与分页

- 作业 ID 是池内递增数字的字符串，同时保存主机和资源池身份。CoRAgent 工作区 Job ID
  属于另一命名空间。
- `online` 只证明联系到了守护进程，不证明每个进程都刚刚被独立核实。`source` 为 `daemon`
  或 `ledger`，`state_basis` 始终是 `ledger`。`observed_at` 是生成视图的时间，并非逐个
  检查进程的时间。离线标记 `stale=true` 并保留 `last_heartbeat`（可能为 null）；历史
  `running` 不能作为进程存活证据。
- CPU 预算是逻辑 CPU 数，`cpu_cores` 是采样核当量；所有 `_mb` 内存字段单位是 **MiB**，
  时长单位是秒，时间戳是 UTC ISO 8601。缺失值为 null 或明确标记 unavailable，不能解释成零。
- 检查 `job_usage.complete` 与总量字段判断当前采样是否完整；逐作业使用 `usage.available`、
  `stale`、`sampled_at`、`final`。未检查覆盖范围时，不能把兼容的“新鲜采样之和”当作完整总量。
- `jobs` 默认只列未完成作业，FIFO 顺序；`--all` 含历史、最新优先；仅终态的 `--state` 筛选
  也按最新优先。返回 `order`、`total`、`limit`、`offset`、`has_more`、`next_offset`；
  按 next_offset 继续，直到 null。各页是实时快照，期间提交或状态改变可能使行移动；
  按 ID 去重，必要时重新扫描，不能当作冻结的全量导出。
- `logs` 返回有界的 `text`、字节 `offset`、`identity`、`eof`、`reset`、`finished`。
  用返回的 `--offset`、`--identity` 继续读取，追加内容不会重复返回；文件变化或截断时
  从零重新读并设置 `reset=true`。UTF-8 不完整／非法字节会替换解码，这是文本视图而非二进制导出。
- 取消成功仅表示 `accepted=true`。继续查询 `show ID --json`，确认 `job.execution_finished`、
  `state`、`cancel_requested`、`cleaned`。完成结果可以先于取消生效，`unknown` 仍保留资源；
  调度成功不代表科学结果有效。

### handler 协议与恢复

`qrun --state-dir /绝对路径/资源池 handler` 从 stdin 读取一个 JSON 对象，返回一个
`coragent-external-job/1` 响应。原有响应结构及协议错误返回退出码 0 的行为保留，
不加入 CLI 元数据；必须读取 `error`，不能只看退出码。提交／状态契约另见
[External Jobs](EXTERNAL_JOBS.md)。

提交请求示例（路径必须已经存在于执行主机允许的工作根目录内）：

```json
{"schema_version":"coragent-external-job/1","action":"submit","request_id":"example-001","job_id":"example-job","cwd":"/srv/qrun/jobs/example","script":"/srv/qrun/jobs/example/run.sh","resources":{"cpus":1,"memory_mb":512},"timeout_seconds":60}
```

发送前保存完整请求。成功回执提供 `scheduler_id`；回执丢失时保留所有身份字段
（`request_id`、`job_id`、`cwd`、`script`、`resources`、`queue`、`timeout_seconds`），
仅把 `action` 改成 `recover`。找到记录时返回原编号，不要生成新 request_id 重试。
查询和取消使用相同身份字段，加返回的 scheduler_id，action 分别为 `status`、`cancel`。
同 ID 不同内容会被拒绝。`found=false` 只是当时未找到记录，不授权创建新身份；
重复发送同一合法提交身份仍由守护进程去重。

人工命令和 handler 共用队列实现：

| CLI 命令 | handler action 与字段 |
| --- | --- |
| `status` | `overview`（handler 的 `status` 需要完整作业身份） |
| `resources` | `resources` |
| `jobs` | `jobs`：`all`、`states` 数组、`limit`、`offset` |
| `show ID` | `show`：`identifier` |
| `logs ID` | `logs`：`identifier`、`stream`、`bytes`，可选 `offset`、`identity` |
| `pause`、`resume` | `pause`、`resume` |
| `config` | 读取用 `overview`；修改用 `configure` 加 `cpus` 和／或 `memory_mb` |
| `cancel ID` | `cancel_job`：`identifier`（handler 的 `cancel` 使用完整作业身份） |

所有 handler 请求都带 schema_version，且要求守护进程在线；只读离线回退属于人工命令层。
`maintenance`、`serve`、`_run`、`_portable-run` 和 `service ensure` 是安装器／守护进程入口，
不是另一套提交 API；完整帮助可以发现它们，机器提交仍应使用 handler。

## 运维

使用安装返回的 program、同一 `--state-dir`，执行 `jobs`、`list` 或 `cancel 4`。完整账本导出用 `list --json`。
CoRAgent 普通 Job 的状态、取消、恢复、回收接口保持可用。队列记录包含本机路径，应保密。

独立安装的队列升级时先排空／取消作业、停止队列服务，再用原配置执行 install；活动服务通过锁拒绝
重新安装。init/install 不覆盖已有池配置。日常调整预算使用在线 `config` 命令，
无需排空或停止，不要直接编辑运行中服务的 config.json。不要通过删除账本解决结果不明的作业。
移除时先排空／取消，停止并禁用记录中的 unit，删除 unit_path，再执行
`systemctl --user daemon-reload`；按需要保留历史。卸载 CoRAgent 不会移除独立安装的队列
或停止其计算。

确定性测试覆盖 FIFO、资源竞争、取消、响应丢失、重启、超时、真实脚本和模拟 SSH。
system-services 通道使用已登记、隔离并审计清理的真实服务，验证资源限制、恢复及
脱离进程组的后代取消。测试不代表已连接或部署到某台实际远端服务器。
