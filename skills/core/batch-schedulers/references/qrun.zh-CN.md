# Qrun 本机与 SSH 执行

Qrun 在执行主机上提供持久化的单个 CPU／内存 FIFO 资源池。
配置 `executor="qrun"`，独立选择 `transport="local"` 或 `transport="ssh"`。
已安装的独立 handler 使用与集群适配器相同的外部 Job 协议，无需在 Skill 中另写一份脚本。

## 内容

- [配置与检查目标](#配置与检查目标)
- [提交、观察与恢复](#提交观察与恢复)
- [队列控制](#队列控制)

## 配置与检查目标

```toml
[execution.platforms.compute]
default_scheduler = "main"
schedulers.main.executor = "qrun"
transport = "ssh"
ssh_host = "YOUR_SSH_ALIAS"
storage.work_root = "/home/USER/DATA/qrun-jobs"
storage.file_mode = "staged"
schedulers.main.handler = ["/home/USER/soft/Qrun/qrun", "handler"]

[execution.platforms.compute.schedulers.main.submission.resources]
cpus = 4
memory_mb = 4096
walltime = "01:00:00"
```

路径替换为实际安装资源池的路径。示例假定已有绑定状态目录的包装器；没有包装器时，
使用安装器返回的完整 handler 参数数组。本机执行改为 local 并省略 ssh_host。
工作根目录必须在该资源池允许的范围内。staged 传输需要两端有 rsync；shared 模式
需要验证路径可见性。科学软件绑定单独指向执行主机上的环境。

通过 CoRAgent `job_probe` 检查目标可达性，其 `queue` 字段提供资源总览；
计算软件另行通过所选绑定的环境检查核验。
主安装器可为明确配置且使用默认 handler 的本机 Qrun 入口准备资源池；
没有执行配置时不创建资源池，SSH 池需显式托管。
安装和守护进程管理见 [Qrun 运维](../../../../docs/QRUN.zh-CN.md)。

## 提交、观察与恢复

普通 CoRAgent 计算使用 `job_start`、`job_status`、`job_reconcile`、`job_cancel`、
`job_collect`。每次提交明确申请正数 CPU 和内存，不超过池总容量。
Qrun 不支持命名队列、GPU 分配或 PBS select。

Qrun 作业编号为池内递增数字，例如 `12`；回执的 `scheduler_id` 为字符串 `"12"`。
同时保留目标／资源池身份。CoRAgent 工作区的 `job_id` 是另一种身份：CoRAgent Job
命令使用工作区 ID，Qrun 原生命令使用数字编号。提交响应不确定时恢复原请求，不生成
新请求重复提交；不通过编辑账本处理未知执行状态。

在目标主机使用已安装包装器，或程序加 `--state-dir` 执行以下命令。
SSH 使用配置的主机别名加相同命令：

```sh
qrun resources --json
qrun jobs --json
qrun jobs --all --state failed --limit 20 --json
qrun show 12 --json
qrun logs 12 --stream stderr --bytes 4096 --json
qrun watch --count 1 --json
qrun cancel 12 --json
```

自动化应解析 JSON，不解析彩色表格。操作命令的 JSON 新增 `cli_version="qrun-cli/1"`、
`ok`、`command`，原有查询字段位置不变。同时检查退出码与 ok；错误包含 `code`、`retryable`、
`action_outcome`、`recovery`。retryable 不授权重复修改，回执丢失后先查询当前状态。
使用有限分页，按 next_offset 继续直到 null；期间数据可能变化，要按 ID 去重。
`list` 保留旧的全量 JSON 数组，但无新鲜度标记，观察状态优先用 `jobs --json`。
日志续读传返回的 `--offset`、`--identity`，轮转后检查 reset。
`watch --json`、`logs --follow --json` 输出 JSON Lines，普通 AI 检查不要使用无限跟随。
通过 `--help-all` 发现机器接口；独立 handler 保留 `coragent-external-job/1`，协议错误仍返回
退出码 0，必须读取 error。handler 的 status 需要作业身份，资源池总览使用 overview。

预算、预留、可派发属于调度账本；主机可用量和实际采样用量是不同指标。
starting/running/stopping/unknown 都保留预留。OFFLINE/stale 是历史证据，不是实时进程检查。
通过 show 的 wait_reason 判断暂停、资源不足、fifo 前序阻塞（blocked_by 也是数字编号）、
超过缩容后容量或等待派发。严格 FIFO 不回填。取消已接受不等于已停止，要通过 show 确认 `job.execution_finished`、终态和 `cleaned`。
`online=true` 只表示联系到了守护进程，不是逐进程存活保证；状态都来自账本。
缺失／过期采样不代表零：检查 `job_usage.complete` 和可空的 `total_cpu_cores`、
`total_memory_mb`，兼容保留的 CPU／内存采样之和可能只覆盖部分作业。

日志优先读暂存作业的应用 stdout/stderr，否则读取直接脚本的捕获输出。
旧作业可能没有日志或用量。用 job_collect 回收声明的计算输出，并独立验证计算结果；
调度成功本身不代表科学结果正确。

## 队列控制

`pause`/`resume` 控制新作业派发，运行中作业和回收继续。
`config --cpus N --memory-mb M` 在线调整预算，不杀已有作业。
缩容可能产生超预算预留，或超过容量的 FIFO 队首；修改共享池前说明这一影响。
portable 的 cron 会重新启动已退出服务，所以 service stop 只是临时停止。
代码升级需要排空，日常预算调整无需排空。

portable 使用 CPU affinity 和进程树 RSS 采样超限终止，不是内核内存硬限制；
现代 systemd 方式使用 cgroup v2。用户可以通过 PBS 独占节点，同时独立管理常驻 Qrun；
不能仅凭 PBS 占位推断 Qrun 跟随 PBS 生命周期，或受到其 cgroup 保护。
