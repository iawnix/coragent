# Research Memory 架构

本文描述 CoRAgent 当前运行时与 Research Memory 的职责边界。验证和发布流程见[维护指南](MAINTAINER_GUIDE.zh-CN.md)。

## 所有权

CoRAgent 只使用 Pi 原生 Harness 循环。Workspace 是跨会话存在的研究容器；Research Memory 组织原始要求、局部问题、多次尝试、显式关系与产出，不负责科学调度或自动证明结论。

| 组件 | 负责 |
| --- | --- |
| Agent Server / Host | 整体服务宿主；Host 负责工作区准入、认证、会话路由与 Worker 恢复发现 |
| Pi SessionWorker / durable Harness | 会话存储的唯一拥有者，负责对话、模型/工具执行、原子输入接纳与恢复 |
| Research Memory | Workspace 存储合同、原始要求、Node、不可变 Result、显式研究关系 |
| Job Manager | 派发、执行、取消、核对、收集、后台跟踪和可靠事件投递 |
| Artifact Store | 不可变文件及来源 manifest |
| Task Controller | SessionWorker 内的用户任务意图、生命周期和推进策略 |
| Monitor | Task、Run、Job 的统一管理面板与 API，不另建调度状态 |
| Email Skill | 已授权报告投递、附件固定和运输回执 |
| 检索 / Web | 可重建的预算内视图、排序理由和只读导航 |

唯一研究命名空间是 `research_agent.research`。运行适配层组合 Memory 与 Job/Artifact DTO；Memory 不导入执行器或 `research_agent.application`。共享事务和文件 IO 属于 `research_agent.foundation`。`runtime-bridge` 只传输命令，不维护另一套文件模型。

## 研究模型

Node 承载持续推进的局部问题。goal 是问题，proposal 是当前假设或思路，plan 是调查方案，progress 是进展说明。假设可为空；调参数、换构型、同目标重试通常留在原 Node。独立问题才另建 Node，不要求模型创建 Attempt 对象。

复杂研究以可独立解释的问题及现有 `part_of`、`requires`、`alternative_to` 关系组织。根节点可选，共享问题可以有多个父节点。`coragent-user-task/5` 的研究范围由 `research.entry_node_ids` 与 `research.focus_node_ids` 组成，通过 `task_update` 的 `set_research` 动作一起替换。这些是导航引用，不是所有权、执行顺序或第二份计划。Node 与 Result schema 保持不变。

Node 状态为 open / paused / closed。关闭表示停止主动推进，不表示科学成功，也不取消 Job。内容修订号独立于后台执行观察；并发修改需要重新读取并明确合并，单纯追加笔记不覆盖其他人的判断。

Result 固定有价值的观察、判断、限制、输入版本、证据和文件，可为否定或证据不足。Result 不可变；用 supersedes 明确修正并保留旧版。Node 的 assessment 是明确选定的综合判断，不默认采用最近结果或失败。上游修正产生精确复核提示，不暗中替换下游输入或重新计算。

## 关系与来源

part_of、requires、alternative_to 由 Agent 明确声明，单次保存；反向关系与 map 索引自动生成。包含关系不能成环；反馈和竞争路径不要求整个 map 是 DAG。相互等待产生诊断，不成为工具准入关卡。

uses / cites 必须来自确证材料输入或明确结果引用。文件名相似、字节相同、浏览或检索均不能证明采用了某个科学来源。Result 引用具体的既有版本，研究反馈不造成证据循环；无法证明的来源保持未追踪。

## 模型接口

| 工具 | 最小请求 |
| --- | --- |
| research_read | `{}` 读上下文，`{ref}` 读精确对象 |
| research_search | `{query}` |
| research_create | `{goal}` |
| research_update | `{node_id, note}` |
| research_result | `{node_id, conclusion}` |

更新可按需修改思路、方案、进展、状态、综合判断及关系。结果文件引用已登记 Artifact。Session、工作区、请求身份、读取依据和版本由可信适配层提供；模型不维护事务字段、反向边或全局 progress。没有回合末 checkpoint 或强制 disposition 补写。

## 工作区与存储

`workspace_manifest.json` 使用 `research_workspace/3`。研究记录保留用户原文，并区分研究作者和运行事实来源。`research/nodes/<id>/` 保持稳定目录、当前视图与工作文件；不可变结果和历史保存旧版本。索引、反向查询与 Markdown 可重建，改标题或关系不移动目录。

研究对象使用工作区内按类型递增的编号（`task_1`、`node_1`、`job_1`、`result_1`、`art_1`），工具、存储和客户端使用同一正式 ID，没有显示别名。`operations/identifiers.json` 持久保存各类型的序号；失败不回收已预留编号，重试复用原身份，允许空号。内容校验仍使用哈希。新工作区使用版本 3 manifest，旧工作区不迁移。

`runs/jobs/` 是执行工作目录；`operations/` 保存意图、观察、收集/投递回执和精确短引用；`artifacts/<id>/payload` 及 manifest 保存固定文件及来源。可变工作文件登记后才能成为正式结果材料。报告仍是面向用户的文件，实际交付版本固定。

事务保证完整更新和中断恢复。旧图与 notebook 工作区均明确拒绝，不迁移、不改写。新建工作区并显式导入材料，没有双协议读写层。

## 上下文与 next_run

上下文预算先保留原始要求与认证触发原因，再按事件归属、明确焦点、待处理执行事实和研究关系选择 Node，并补充必要的结果及直接依赖。省略内容提供读取/检索入口，不视为完成。普通用户文本不能冒充 Monitor 元数据。

Research Context 是 Agent Runtime 内部的上下文准备模块。每个 generation 边界通过 `research_read view=brief` 读取本地确定性概览，比较当前范围和相关事实指纹；首次进入、范围变化或事实变化才追加 pi.context，并与请求截止位置原子提交。无关研究变化和重复事件不重复注入。输入来自哪个组件不决定刷新。读取和无变化判断通过 memo 固定，失败在新输入边界重试。

Research Brief（research-brief/1）整理范围内事实、矛盾、未知项、限制和原始引用，指纹包含因大小限制而省略的候选记录。通常以 2,000 tokens 为目标，出现矛盾可扩至 4,000。运行事件同步是否完整与模型综合摘要是否成功分别记录；结果、终态 Job 或矛盾可触发无工具的模型综合，失败保留基础概览。概览和摘要均不授予写权限，也不证明科学有效性。完整证据通过 research_read、job_status 等工具读取。详见[研究上下文](RESEARCH_CONTEXT.zh-CN.md)。

`CompactionTask.prepareSummary` 只从选定的不可变旧历史范围生成指引和元数据。补充材料在原生摘要调用前固定，重试和恢复保持一致；摘要记录保留非模型可见的范围标记，后续完整历史中的新背景优先。不读取最新研究状态并倒填到旧摘要，不从摘要推导授权或读取凭据。Pi 继续负责安全切分、摘要调用、重试、用量记录以及原子提交和过期判断；reset 会重新建立背景。

固定规则留在 system，历史 research_context 在原位置以 user 消息载体承载数据。每次请求只在末尾附加小型 runtime_control，提供任务身份、revision、控制状态、等待对象及真实用户提交 ID；外部 IO 后复核执行授权。两种数据载体都不是用户授权。不再另行运行每请求研究快照机制，也不要求模型编写记忆协议。

上下文准入遵循 Pi 原生的压缩策略：在 `contextWindow - reserveTokens` 处进入阻塞压缩，Pi 的 reserve 会为回答和提示开销预留空间。`CORAGENT_CONTEXT_INPUT_TOKENS` 只在受限部署需要额外限制输入上限时显式设置，默认不再设置。默认的后台压缩和近期历史保留使用 Pi 的配置；显式设置输入上限时，近期保留目标最多占其三分之一，后台压缩最多提前 8,192 tokens。最多尝试一次阻塞压缩；保留消息过大或压缩失败时，在主模型调用前停止。`research-request-context/4` 诊断只保存大小和摘要指纹，不复制完整快照。估算和 cache 统计不代表账单；本变更不迁移历史文件。

终端同时展示模型窗口与运行输入预算。排队的被动写入（包括后台压缩摘要）不再阻止续接失败的结算，预算拒绝会进入执行待处理状态，不会一直显示准备续接。显式恢复后，由 Pi 在原生边界先处理这些写入，再消费新输入；排队的用户输入仍优先处理。

研究 Job 提交时明确绑定 node_id 和已读方案版本；可信工具适配层同时绑定当前 `user_task_id`，与科学 Node 归属分开。准备与诊断可以没有归属。Monitor 事件跨 Node 修改和会话重启保留提交时关联。

next_run 是实际调度模式：持久化认证执行事件，会话忙或自动执行暂停时保留；可接收时幂等提交一次 Pi 输入。事件保存、Pi 消费和科学解释是不同事实。回复丢失沿用请求身份；固定批次重试时不吸收新事件。普通笔记、Node 状态和 Memory sequence 不触发或抑制投递；Node open 本身不产生自动输入；另行登记的活跃用户任务即使没有新 Job 事件也可以继续推进。

## 持久用户任务与 Monitor

请求阶段的任务事实与研究内容共用预算；有界浏览投影仍将省略详情指向 `task_read`。用户任务跨越多个 Pi run 和计算 Job。`task_begin`、`task_read`、`task_update` 保存已授权目标、用户提交来源、交付条件、进展证据和具体等待/阻塞。普通问答不自动建立任务；每个 session 最多一个非终态用户任务。任务控制状态只存在 Pi durable 文档中，Host 不另存任务状态机或控制回执。

Workspace、Research Memory、Task 与上下文管理保留完整研究核心的内聚。普通 Task 的计算目标、
选择与策略初始均为 null，不解析平台。实际需要计算时，task_update action=bind_execution 与明确
提供执行字段的 task_begin、首次 set_execution_plan 共用唯一解析器。准备与提交要求已持久化绑定；
本地 bash 和平台诊断不要求绑定。Task 始终只有一套协议和一份 Pi 管理的生命周期。
研究读取在应用组合层读取本地 Job 观察并重放已保存事实，不查询外部队列；已有 Job 使用原记录路由，
不随当前平台配置变化而改道。

Task Controller 位于 SessionWorker 内。普通工具工作继续使用原生 Pi 循环；run 正常结束后，活跃且空闲的任务通过同一输入接纳事务提交 `task_controller` 内部输入。当前实现不安装 `onYield` 延续路径。watch 和 30 秒核对恢复推进责任；等待只查询实际归属 Job，条件未满足时不请求模型。无新证据轮数仅作为模型重新评估方法的提示，不自动阻塞研究。临时模型服务故障可按配置退避，以新的 Pi 输入进行有限恢复；不可重试或额度耗尽时记录执行待处理，研究任务保留 active 或 completing。最终回复恢复保留完成证据，仅允许读取与回复。回复结束不代表研究完成：完成提议必须覆盖全部交付条件的证据，并且最终回复成功交付。

暂停只抑制后续自动执行，当前回复和已有 Job 可以收尾；用户打断回复会同时暂停任务。恢复是用户控制操作。取消任务须显式选择保留还是请求取消已有 Job。Monitor 查询不发送模型输入或恢复任务。`CORAGENT_AUTOMATIC_CONTINUATION=0` 关闭自动输入，保留用户输入与状态读取。

研究执行失败后，新的用户请求运行期间，Monitor 详情保留失败原因。底部状态行使用
[终端文档](TERMINAL.zh-CN.md)中的五个简短标签，恢复细节在面板内查看。仅接收消息不会恢复自动研究；当前用户 run 记录了新的任务证据或归属 Job 里程碑，并由 Pi 确认提交成功结束后，控制器清除旧的研究恢复警告，允许后续续接（或遵守当前 Job 等待）。重复证据、状态询问、被新输入替代的请求和失败 run 都不能清除警告；暂停与取消仍优先。恢复关联可跨重启保留，历史失败提交不被改写。

自然语言任务控制使用 `task_update action=apply_user_control`，引用当前 run 已消费的最新真实用户提交。运行时校验来源、当前输入归属及修订号；自动输入不构成控制授权。处理停止指令的 run 可以完成只读核实、用户要求的 Job 取消与最终确认，但不能继续发起工作或创建替代任务。Task 取消先于 Job 查询与取消落盘；后端故障保留为持久化清理工作，不唤醒模型。取消 Job 或修改 Node 状态都不会停止顶层 Task。

自动观察与显式进展更新共用持久身份集合：单项 Result ID、Artifact 内容摘要及归属 Job 的里程碑。改计划、追加 note、新建 Node 和换焦点记录活动但不补充进展额度；复用身份、换引用组合或重启也不补充额度。每项完成条件需要固定 Result 或 Artifact 证据，科学适用性仍由 Agent 判断。这些控制不能判断新产出是否具有科学价值。

Host 重启从 Pi 现有 session catalog 发现会话，最多并行恢复四个 Worker；每个 Worker 核对自身 durable 任务。恢复失败通过 `monitor/health` 展示。只有 SessionWorker 写会话 SQLite；聚合视图来自 Task、Pi、Job 各自事实源，不声称跨系统原子快照。

`/monitor` 统一展示任务、作业和执行详情。Host 与浏览器共用 `apps/agent/contracts/monitor.mjs` 的唯一方法目录，请求与返回见 [Monitor 合同](../contracts/monitor/README.md)。Pi generation/tool Task 位于 run 的诊断详情中，不列入用户任务。任务/作业变化与重连沿用现有通知读取最新快照。

## Skill 与交付

Pi 原生加载 Skill。CoRAgent 验证安装资源摘要。使用 Pi 提供的真实 Skill 路径，相对引用以该 Skill 目录为基准。research-memory 教五种小操作，research-workflow 协调 Job 和材料，领域 Skill 提供科学方法。reaction_mapping.md 位于 material-preparation/references/。

进程完成、文件存在和 Node 关闭都不证明科学结论。Email 使用已有用户授权和独立投递回执；运输接受后 Memory 记录失败，只恢复记录，不重发。安装、运行和科学结论分别需要对应证据。

职责、执行原因和单协议升级边界见[任务、作业与执行](TASK_JOB_ARCHITECTURE.zh-CN.md)。
