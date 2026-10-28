# 终端

[English](TERMINAL.md) | [简体中文](TERMINAL.zh-CN.md)

`coragent --workspace <name>` 启动基于公开 Pi TUI 组件的 CoRAgent 终端。
CoRAgent 负责会话连接、命令和记录展示，Pi Durable 负责执行及 SQLite 持久化。
终端通过 Host RPC 连接会话。

工作区统一使用 research 模式，启动时无需选择模式。创建或继续工作区的命令见下文。

运行 `coragent -h` 查看常用命令和示例；运行 `coragent --help-all` 同时查看 SSH 参数和后台服务说明。

## 运行边界

```text
CoRHub/Web ── Link/HTTP ──┐
CoRAgent TUI ─ Unix/SSH ────┼─> CoRAgent Agent Server / Host API
Monitor ─ Host RPC ─────────┘       ├─ Agent Session
                                    └─ Harness / Host / SessionWorker
```

Host 是 Agent Server 的 API 和宿主层，负责路由、认证、会话管理 RPC 回执、会话发现
以及 Job Manager supervisor；Harness worker 在同一个 Agent Server 内拥有 agent loop、模型、工具、
transcript、用户任务控制回执和 SQLite durable lane。CoRAgent TUI、Phone、Monitor 都是同一个 lane 的客户端，
不会启动第二个 agent loop。

Host client 的 RPC transport 可以是本机 Unix socket，也可以通过 SSH 启动远端
`coragent-host-proxy`，把同一份 `coragent-host/3` NDJSON 通过 SSH stdin/stdout 转发到远端私有
socket。SSH transport 只改变连接路径，不改变 workspace、session 或 Agent lane 的拥有者。

连接远端安装时，需要同时提供远端 Host socket 和 proxy 路径：

```bash
./coragent --workspace reaction-a \
  --remote-host pi.example \
  --remote-host-socket /ABS/remote-host.sock \
  --remote-proxy-path /opt/coragent/current/agent/apps/agent/transport/ssh.mjs \
  --ssh-config ~/.ssh/config
```

将 socket 占位路径替换为该安装实际的 Host 端点，其目录和文件名包含安装及服务身份。
proxy 示例假定远端软件根是 `/opt/coragent`；使用源码检出时则为
`<checkout>/apps/agent/transport/ssh.mjs`。

启动器会对 Host 返回的 Host socket 再使用同一个 SSH proxy，并给终端客户端一个本地私有
Unix endpoint。workspace 和 session 仍由远端 Host 持有；本地目录只用于 presentation cwd。

## 打开工作区

```bash
./coragent --workspace reaction-a
./coragent --workspace reaction-a -c
```

启动器先确保安装级 Host 在线，再请求 session descriptor，把 CoRAgent 自有终端客户端
连接到 Host socket。Native Pi Harness 是唯一支持的后端，不提供 tmux 或 PTY scraping
路径。同一 workspace 的第二个终端会连接同一个 SQLite durable session；客户端关闭不会
停止 worker，也不会打断当前 turn。

Host 是安装级服务，会扫描 workspace root 下的直接子工作区。通常使用：

```bash
systemctl --user start coragent.service
systemctl --user status coragent.service
```

system service 去掉 `--user`。Host 私有 socket 位于配置的 runtime 目录。

## 会话和操作

终端宽度至少为 110 列、对话区至少有 12 行时，右侧显示研究/Job 侧栏，包括当前任务、
关联问题、下一步和活动 Job。`/sidebar off` 隐藏侧栏，`/sidebar auto` 或 `/sidebar on`
在空间足够时启用。窄终端保留完整对话宽度，通过 `/research`、`/monitor` 查看详情。
任务和 Job 的执行状态不代表科学结论成立。

`/tasks` 查看运行、等待及下次检查时间、排队输入和恢复提示。`/retry [task-id]` 选择或指定
因 Pi 重启次数超限而暂停的执行，从已保存进度继续，不重放已完成的工具。
压缩失败使用 `/compact` 重试；研究任务暂停使用 `/monitor task resume <task-id>`。
状态自动刷新且不调用模型，查询失败会明确标记不可用。

`/image <工作区相对路径>` 通过 Host 预览 PNG、JPEG、GIF、WebP，支持 SSH 远端工作区。
文件上限为 8 MiB、4000 万像素；使用 `inputs/`、`artifacts/`、`runs/`、`reports/`、`outputs/`
下的材料路径，例如 `/image outputs/plot.png`。路径可含空格，无需 shell 引号。读取分块进行并校验文件版本，
Esc 取消后续读取。此命令只预览图片，不向模型提交图片。工具返回或会话消息中的图片也会
显示在对话记录中。Kitty 图形协议显示 PNG，iTerm2 图形协议支持其它图片格式；终端或格式
不支持时显示文字占位。使用 Kitty 类终端时可将图片导出为 PNG。不会自动读取 Markdown
里的图片路径或下载 URL。

CoRAgent 终端 提供 `/resume`、`/model`、`/thinking`、`/compact`、
`/reload` 以及 CoRAgent 命令。`/reload` 刷新模型配置与凭据。`/resume` 只能切换当前 workspace 中的 SQLite durable
session，不会跨 workspace。切换会释放当前 TUI 连接，再附着选中的会话；后台任务继续运行。
独立 Pi 的其它会话命令在这个远程客户端中不可用。

CoRAgent 提供以下客户端命令，名称、参数和补全由同一命令目录定义：

- `/research`：查看当前任务的研究进展、已保存的判断和证据；读取与检索命令展开原始记录，也支持 SSH 连接的远端工作区。详见下文“研究进展”。
- `/sys-prompt`：直接读取当前 worker 的 CoRAgent system prompt manifest 和来源，不调用模型。
- `/resume [session-id]`：在当前工作区选择或指定会话；取消选择保持当前会话。
- `/usage`：在紧凑面板中查看当前会话的 token 总量、上下文和各模型用量。
- `/monitor`：在实时面板中查看当前用户任务、交付条件、等待对象、计算作业和执行记录；完整命令见下文。
- `/quit`：断开当前终端，保留后台 worker 和任务。

无实际诊断功能的 `/debug` 已移除。

Slash 补全在输入框上方使用稳定的候选窗口。上下键选择候选，Tab 或点击只补全，
Enter 打开命令入口；参数候选的 Enter 只补全，再次 Enter 才提交完整命令。
Esc 关闭候选并保留输入，Tab 可重新打开。`/monitor` 按当前参数位置展示子命令和选项，
不会把任务 ID 改成小写，也不会将占位符作为真实参数提交。缺少参数时不执行操作。

命令失败后，如果输入框尚未被编辑，原命令会恢复以便修正；迟到的失败回执不会覆盖新草稿。
错误行保留 `F2 Details` 入口，可查看完整错误与用法；运行时查询错误还显示可用的命令名、
错误码、请求编号与耗时。Esc 返回后保留草稿。支持 Windows Terminal 的标准 F2 序列，
包括在输入超时范围内分段通过 SSH 到达的序列。
路径和以 slash 开头的多行文本按普通消息处理；粘贴本身不会执行命令。

命令面板、选择器和详情页跟随当前 Pi 主题，选中背景与正文颜色来自主题。
`›` 表示键盘焦点，`[current]` 表示已经生效的选项。选择器支持点击和滚轮。
正常运行或排队使用活动色，阻塞使用警告色，执行失败使用错误色，取消使用次级文字色。
详情页区分字段名、数值、布尔值和状态；`/sys-prompt` 为 Markdown 标题、行内代码和代码块着色，保留原文。
诊断详情中的 `[]` 表示空列表，`{}` 表示空对象，`—` 表示未提供值，`""` 表示空字符串。
空集合与字段名在同一行显示；Monitor 空列表显示 `No entries`，这些都不是错误状态。
`NO_COLOR` 或 `TERM=dumb` 下，命令面板、补全、状态栏及工具摘要保留文字与符号提示。

命令成功提示在 3 秒后消失，普通说明在 5 秒后消失；错误保留到关闭或下一次提交。
提交新消息会清除已完成的命令提示。选择器或详情页打开时，`Esc` 先返回聊天；
普通聊天中 `Esc` 暂停当前用户任务，即使任务正在等待计算、没有模型回复，也会发送暂停；
存在运行中的 turn 时同时打断它。临时命令提示不会拦截该操作，已提交的计算 Job 保持运行。

底部 Context 独立于 Monitor 和研究查询刷新。历史变化后，用量暂时显示 `Updating`，
直到取得匹配的估算；同一模型已知的窗口容量继续显示。请求失败时显示
`Unavailable`，原因可在 `/usage` 查看。切换模型后不沿用旧模型容量。
`Total tokens` 是会话累计用量，不是当前上下文占用。

用量、监控、模型、思考等级、会话选择面板，以及 slash 补全列表，均在 Monitor 行上方展开。
系统提示词和较长的研究结果替换上方阅读区域，标题和返回/滚动提示固定。
所有界面都保留底部 Monitor、输入框和模型/上下文信息；面板打开时保留输入草稿和光标位置，
输入框暂时不可编辑，点击也不会抢走命令焦点。
上下键只滚动内容，不改变面板高度；短文档只显示返回提示。
关闭后恢复输入草稿、光标和聊天阅读位置；面板打开期间隐藏后台任务的取消快捷键提示。

输入框正上方的常驻行分别显示 Monitor 连接、用户任务状态和计算作业数：

`Monitor: Connected · Task: Waiting for compute · Job: 1 running, 0 queued`

`Monitor` 表示当前会话的监控快照是否可用：

| 显示 | 含义 |
| --- | --- |
| Connected | 已成功取得当前有效快照 |
| Connecting | 等待首次快照，切换会话后也需重新取得快照 |
| Disconnected | Monitor 概览请求失败 |
| Unknown | 快照缺少有效时间戳，或超过 30 秒未更新 |

取得当前有效快照前，`Task` 和 `Job` 显示 `Unknown`，不把其它会话或过期快照中的
缓存数据当成当前事实。这些连接和时效状态不表示研究或计算作业已经暂停、停止。

`Task` 直接显示持久化的 `task.state`，与任务详情和列表使用相同标签：

| 任务状态 | 显示 |
| --- | --- |
| `active` | Researching（研究中） |
| `waiting` | Waiting for compute（等待计算） |
| `paused` | Paused（已暂停） |
| `blocked` | Needs attention（需要处理） |
| `completing` | Preparing delivery（准备交付） |
| `completed` | Completed（已完成） |
| `partial` | Partially completed（部分完成） |
| `cancelled` | Cancelled（已取消） |
| `recovering` | Checking recovery（检查恢复） |

有效快照中没有任务时显示 `Task: None`。控制器查询失败、关闭自动推进或执行恢复
不会将任务状态改显示为另一种活动标签；具体说明保留在 `/monitor`、任务详情、执行记录
与 `/monitor health` 中。一轮模型回复结束不代表用户任务完成。

`Job` 分别统计运行中和排队中的计算作业；有当前任务时统计该任务，否则统计本会话。
数量覆盖全部分页，不表示模型是否正在回复。不推算完成百分比或时间。
没有运行作业、打开选择器或阅读页时也保持显示。后台刷新保留焦点、选择、阅读位置和输入草稿。

`/monitor` 概览提供紧凑的实时摘要，展示任务状态、目标、最近进展、具体 Job 等待条件、恢复原因、
下一步、恢复条件和实际推进状态。暂停、阻塞或关闭自动推进时，不显示“就绪后自动继续”。
Job 数量统计当前任务的全部分页；没有当前任务时统计本会话。最多预览五个运行中或排队中的 Job。
长摘要会提示查看完整详情。用 `/monitor task <id>` 查看交付条件与研究详情，
用 `/monitor jobs` 查看执行和收集状态，用 `/monitor run <id>` 查看 Pi generation/tool Task。
Job 成功不直接等于科学分析完成；应读取已记录的 Result 和证据，Research Brief 只提供导航概览。

启动时，`-c` 选择当前 workspace 最近的可写 SQLite durable session，`--session-id <id>` 选择
指定 session。顶层 `-r`/`--resume` 会被明确拒绝，因为 Host-mediated client 必须先取得
确定的连接 descriptor 才能启动 TUI；请先进入终端，再执行 `/resume`。Phone/browser gateway 的
prompt 通过 Host `input/send` 进入同一个 lane，并使用持久回执和稳定的
`client_message_id`。

输入历史从当前 session 的活动 transcript 恢复，并按 session 隔离；切换会话后可用编辑框的上下
方向键查找已接受的 prompt。重新打开时，压缩之前已不在活动 transcript 中的输入暂不恢复。

分离、打断和退出不是同一件事：终端 detach 只是客户端断开；聊天中的 `Esc` 暂停当前任务，
包括等待计算时；Host 的 `turn/interrupt` 针对指定的活动 turn。两者均抑制自动推进。
`/quit` 仅关闭当前终端连接。输入发送后若响应丢失，用相同
`client_message_id` 查询 `input/status`。Pi 持久 submission 负责接收与完成状态；
同一业务 ID 重试不会再产生一条输入。

## 研究进展

| 命令 | 行为 |
| --- | --- |
| `/research` | 查看当前任务关联研究的进展，并提供其它研究问题的入口 |
| `/research read [ref]` | 按标题选择研究问题，或读取指定问题、判断或 Result 的完整内容 |
| `/research search [text]` | 按文本查找已保存的研究与证据；省略文本则浏览最近记录 |

标题列表和检索结果会提供下一页命令，并支持按记录条数指定 `--offset` 与 `--limit`。
`/research read --offset <n>` 用于翻阅问题标题列表。读取指定记录时自动加载完整详情，
不接受分页选项。检索按不区分大小写的字面子串匹配，并预览相关研究正文；
以选项名称开头的检索文本可放在 `--` 后面。

概览先展示研究目标和已保存的当前判断，包括判断的限制；随后展示已有证据、
下一步、阻碍以及已记录的用户待处理事项。研究问题以标题导航，记录编号用于
精确打开对应证据；更新时间说明展示内容是在何时保存的。

概览聚焦当前任务关联的问题，其它问题仍提供标题与读取命令。尚未保存判断时
明确提示，不根据 Job 的退出状态推断结论。出现新证据，或者当前判断引用的
Result 已被取代时，标明需要复核，避免旧判断看起来已经包含最新进展。

这些命令由当前 worker 读取持久化记录，不调用模型，不修改研究、任务焦点或恢复
已停止的任务。任务状态、科学结论和计算 Job 状态分别展示：任务停止不表示研究
已经完成，Job 成功也不表示结论有效。任务控制使用 `/monitor`，作业执行状态使用
`/monitor jobs`。文本检索用于找到已有记录，不会生成新答案，也不能替代阅读原始证据。

## Phone、浏览器与 Monitor

Phone 客户端必须通过 CoRAgent Link 使用版本化 `coragent-host/3` NDJSON 方法。Relay 只转发不透明
帧，不拥有 session 或 Research Memory。可选 browser gateway 只附着一个已经存在的会话，
通过 loopback HTTP/SSE 提供 snapshot 和事件，不启动 Pi 或 worker。这个传输 gateway
与只读的 [CoRAgent Web](../apps/web/README.zh-CN.md) 研究浏览器分开，后者不提交 prompt。

Host 握手仅接受 `protocol: "coragent-host/3"`，v1 客户端必须更新。能力列表与调用方法统一用斜杠。
会话读取和附着只接受 `after_cursor: {epoch, sequence}`；Host epoch 改变时返回当前快照，
不重放旧 epoch 的事件。会话创建/恢复及 `model/select` 统一使用 `model: {provider, id}`。
会话列表只返回 `{sessions: [...]}`，不携带旧 backend 或格式标记。

Monitor 统一用户任务控制与计算作业观察。Task Controller 在 Pi SessionWorker 中运行，
沿用 Harness 的 durable 事务与输入接纳边界；安装级 Job Manager worker 观察 Job 状态并登记执行事件。
模型/工具循环始终由 Pi 持有，科学证据与结论仍归 Research Memory。

| 命令 | 行为 |
| --- | --- |
| `/monitor` | 当前会话的实时概览 |
| `/monitor tasks` | 当前与历史用户任务 |
| `/monitor task <id>` | 目标、交付条件、研究问题、进展及等待条件 |
| `/monitor task pause <id>` | 暂停自动推进，当前工作可以收尾 |
| `/monitor task resume <id>` | 恢复指定用户任务 |
| `/monitor task cancel <id> --keep-jobs` | 取消用户任务，保留其计算作业 |
| `/monitor task cancel <id> --cancel-jobs` | 取消用户任务，并请求取消其计算作业 |
| `/monitor jobs [--task <id>]` | 会话内作业或指定用户任务的作业 |
| `/monitor job <id>` | 作业执行与收集状态 |
| `/monitor job cancel <id>` | 请求取消一个计算作业 |
| `/monitor runs [--task <id>]` | 按 Pi submission/run 分组的执行记录 |
| `/monitor run <id>` | 有界读取 generation/tool 执行详情 |
| `/monitor health` | Task Controller 与共享 Job Manager worker 健康信息 |

`/monitor health` 分别展示 worker 最近成功观测与事件投递的时间
（`last_successful_observation`、`last_successful_delivery`），以及对应错误
（`last_observation_error`、`last_delivery_error`）。成功时间为 null 表示 worker 启动后
尚未记录成功。查询超时保留最近观测到的 Job 状态，不表示作业失败；某个平台查询缓慢时，
已有待投递事件仍可继续处理。

任务详情展示研究入口、当前关注问题、局部方案摘录、问题原始状态、assessment/Result
引用和相关 Job。只有当前会话归属的 Job 提供 `/monitor job` 命令；其它 Job 保持可见，
并标注 `Outside this session`（不属于当前会话）。共享问题只展示一次，关系通过 ID 引用同一问题。`closed` 显示为
`Ended`（已结束），不表示科学验证成功或用户任务完成。快照省略的内容会明确标注，
可用 `/research read <id>` 继续读取原记录；节点数量不代表研究完成比例。查看不会
修改任务焦点或唤醒模型，也没有单独的规划命令。

列表和 run 详情支持 `--limit <1–100>`、`--cursor <cursor>`，返回的下一页命令保留过滤条件与页大小。
所有 ID 属于当前会话；缺失或跨会话 ID 返回错误，不自动选择其它对象。取消用户任务必须明确 Job 处理方式。

命令直接调用统一 Host 方法：`monitor/overview`、`monitor/tasks`、
`monitor/task/read|pause|resume|cancel`、`monitor/jobs`、`monitor/job/read|cancel`、
`monitor/runs`、`monitor/run/read`、`monitor/health`。只读查询不提交 Agent 输入或调用模型。
任务控制先读取当前 revision，再携带稳定请求身份提交；版本冲突直接显示，不静默重试。
原有 Monitor status/list/enable/disable 方法及按 Job 切换自动跟进的开关已移除。

暂停用户任务阻止新增自动推进，但不取消其运行中 Job。聊天中的 Esc 暂停任务并停止已有回复，
`turn/interrupt` 针对指定活动 turn；两者均抑制自动重启。Monitor 面板里的 Esc 只关闭面板。
取消 Job、关闭终端是独立操作。
`/resume` 用于切换会话；`/monitor task resume` 才是恢复当前会话内的任务。

Job wake 与用户通知分别记录回执，带租约和退避。wake 只是“输入已接受”，不代表研究分析已完成。
Task Controller 在继续执行前核对持久任务与 Job 状态；Agent 仍须检查结果，Monitor 不发布科学结论或修改 Node。

`workspace_manifest.json` 中的规范 `workspace_id` 同时绑定科学状态与 Host
路由；不存在独立的科学身份或直接目录 alias 映射。

## 会话存储

`<state_root>/pi/sessions/` 是 Native Pi Harness 使用的唯一 session 存储。
workspace `.pi/sessions` 历史不是受支持的输入，Native runtime 不会 resume 或导入它；持久历史位于 `<state_root>/pi/sessions/<workspace-id>/<session-id>/session.sqlite`，旁边的 `meta.json` 保存路由元数据。
研究状态应保存在 workspace Research Memory；SQLite durable session 使用 Host 的会话控制接口。

详见[架构](ARCHITECTURE.zh-CN.md)和[安装说明](INSTALLATION.zh-CN.md)。

### 流式更新与动画

终端以 `presentation: "terminal"`、`view_stream: true` 调用 `session/attach`，
首次返回完整视图，之后通过 `session/view` 推送带序号的历史条目变更和文档更新。
序号不连续时重新连接并获取完整快照；正常流式输出不再调用 `session/query`。
Worker 到 Host 也使用增量传输，手机端继续使用现有快照与事件协议。
文档增量在字段级别发送；例如新 token 不会重复传输未变化的工具列表和运行状态。
文档字段减少时发送替换标记，客户端会删除旧字段，不把已结束的状态留在界面中。

工作动画使用 Pi 公开的 Loader，位于固定状态行，独立于模型输出刷新。
打开面板、执行结束或退出终端时停止动画定时器。
设置 `CORAGENT_TUI_ANIMATION=0` 可使用静态状态文字。
动画和输入刷新复用聊天排版结果，流式文字复用已完成的历史及当前 Markdown 组件。
未变化的历史不参与每次流式更新的条目比较；工具进度只更新对应卡片。
折叠工具的隐藏输出继续接收，展开时展示最新内容，隐藏文字变化不重新排版聊天区。
隐藏侧栏时暂停其 Research 轮询。

阅读历史时，窗口宽度变化按消息及消息内行偏移保持阅读位置；它不保证长段落
重新换行后仍精确对齐同一个字符。点击展开工具卡片会暂停跟随新输出，保持卡片标题
在原来的屏幕位置附近。滚动回底部后恢复跟随。
展开的纯文本工具输出按行复用 Pi `Text` 的布局缓存；追加输出只创建新增行，窗口
变更时仍由 Pi 重新计算宽度。输出会先清理终端控制序列，避免把工具日志当作界面控制码。

`terminal-streaming.test.mjs` 使用 1,000 条历史消息验证流式刷新、窗口宽度变化、
压缩、定时器清理和隐藏轮询；耗时证据保存在本机私有测试目录。
`terminal-experience.test.mjs` 另外验证工具进度、阅读位置、展开行为，以及真实 Pi
全屏渲染器在虚拟终端中的中文输入和粘贴。它记录工具刷新与输入到绘制完成的耗时、
终端输出字节数和整屏清除次数；这些确定性用例不能代替实体终端与真实 SSH 的手感验收。
`terminal-tool-output.test.mjs` 覆盖中文、空行、换行、异常转义、宽度变化、追加与替换，
并验证 150,000 行输出不会耗尽 JavaScript 调用栈。长日志的性能证据仍只保存在
`local_debug/`。
