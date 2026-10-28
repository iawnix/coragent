# Pi 1.4 迁移与回滚

本分支将 Pi 从 1.1.0 升级到 1.4.0，固定提交为
`4a080252f06caf63a525d7873c5d94d3c23887e0`。上游 1.2 删除的实验性
server/client/plugin 栈原先确实位于 CoRAgent 核心调用链；仅修改版本号会使
启动和终端连接直接失败。[此前 1.3 审查](PI_1_3_MIGRATION.zh-CN.md)保留为历史记录。

| 范围 | 本次处理 | 后续风险 |
| --- | --- | --- |
| 会话与 Worker | CoRAgent 维护目录、进程监管、单写者锁、Host RPC 和恢复 | 中：需要持续验证崩溃与关闭竞态 |
| Agent 执行、任务、持久化 | 使用 Pi Durable Harness 与存储接口 | 中：文档 checkpoint、工具 output、提交返回值已变化 |
| 终端 | 使用公开 pi-tui 组件，自行维护命令与会话连接 | 中：布局和键盘行为需端到端验证 |
| SQLite | 自动从 schema 1 迁移到 2，升级前在线备份 | 高：新版数据库不能直接交回旧版 |
| 上游私有接口 | 集中在 `runtime/source.mjs` | 中：模型配置、主题、搜索工具和事务 helper 仍依赖固定源码 |
| 产品策略补丁 | 原二十个补丁合并为四个职责明确的补丁 | 中：升级时必须重新构建并跑行为测试 |
| Host、Phone、Monitor | 保持 `coragent-host/3`，终端也走 Host | 需要客户端兼容测试；不代表真实设备已验收 |

不再使用 `pi-client`、`pi-protocol`、`pi-server` 或 Chord 的 service/facet
网络栈。Pi Durable 仍依赖 Chord 的 context/storage 工具，这与维护已删除的
实验性服务栈是不同的依赖。上游保留在 experimental 目录下的 source-resolver
只用于源码别名加载。详见[补丁责任表](../packaging/coragent_packaging/pi/README.md)。

终端关闭、断线和 `/resume` 不终止正在运行的会话。输入重试保留业务 ID，
Host 和 Worker 共用 Durable 准入记录。压缩只在 summary 实际落入对话后报告
完成；内部 summary 不作为普通回复展示。`/reload` 现在刷新模型配置和凭据，
不再装载上游已经移除的实验性插件。自动补全采用当前公开 Editor 的交互。

## SQLite 回滚边界

首次打开 schema 1 会话时，Worker 在单写者锁内用 SQLite 在线 backup API
保存 `session.sqlite.pre-pi-1.4`，包含已提交的 WAL 页，并保留原目录布局。
备份不会被后续启动覆盖。先备份成功，再让 Durable 执行 schema 2 迁移。

要回到 1.1，先停止整个 Host 及其 Worker，另存当前 schema 2 的数据库和
研究/Job 状态，再将升级前备份恢复为原 `session.sqlite`；确认没有运行中的
连接后处理旧 WAL/SHM 文件。不要只切换软件版本后直接打开新版数据库。
恢复升级前数据库会丢失升级之后的会话记录，而研究文件和实际 Job 副作用
不会随数据库回滚，必须核对二者。正式切换前应为整个安装状态与 workspace
做一致备份。全新 schema 2 会话没有升级前备份。

跨版本演练确认：升级后继续对话会更新 workspace 中的研究上下文与操作记录。
此时仅恢复会话数据库，可能使旧版在准备上下文时失败。回滚必须同时恢复与
数据库对应的 workspace／安装状态快照；实际 Job 和外部副作用仍需另行核对。
Worker 的自动 SQLite 备份只覆盖会话数据库，不能代替整个状态的一致备份。

## 验证范围

本地验收使用确定性模型、假凭据、隔离网络和临时 workspace，包含实际
Worker 工具调用、研究与 Job 流程、Monitor 唤醒、关闭重开、终端输入和压缩。
`tools/test/runner.py` 管理依赖、测试快照及进程清理；结果以当次测试报告为准。
所有测试材料留在 `local_debug/`，不得进入仓库、发布包或外部服务。
真实模型、远程 SSH 和实体 Phone 尚需单独验收，不能从本地测试推断其通过。

`tools/test/pi_upgrade.py` 在隔离网络中使用两个固定产品版本，验证真正的
1.1.0 历史与压缩记录迁移、阻塞研究任务继续执行、生成中断恢复，以及数据库
与 workspace 一起回滚。被杀死的 shell 进程会报告中断；工具场景由确定性模型
显式重试幂等命令，已完成的前置工具不会重放。这不承诺任意外部命令恰好执行一次。
