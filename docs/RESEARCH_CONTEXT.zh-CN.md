# 研究上下文

Research Memory 是持久研究记录。Research Context 是 Agent Runtime 内部的上下文准备模块，
通过唯一的 `research_read(view="brief")` 接口读取 `research-brief/1` 研究概览。
概览由程序确定性选择已记录事实，不再调用额外模型生成综合摘要，也不代表科学评估。
研究记录、工作区与上下文仍属于完整研究核心。普通 Task 没有计算位置时也会建立研究概览；
上下文读取只组合本地研究事实和已记录的 Job 观察，不解析平台或连接队列。Job Manager 负责
刷新外部状态；本地事件投影负责将已持久化事实同步到研究记录，两者不另建一份 Job 状态。

## 恢复时提供什么

Node 用 `goal` 保存研究问题，用 `plan` 保存当前调查方法，用 `assessment_ref` 显式选择
当前判断。Node 第 2 版删除 `proposal` 与 `progress`，不要求把普通记录再复制成一份进度字段。
普通 note 记录尝试、观察和后续想法；Result 保持不可变发布。关系和索引视图继续用于导航与复用。

在获得重要结果、改变研究方向、等待作业或交付之前，可以通过
`research_update(note=..., references=[...], as_assessment=true, plan=...)`
一次原子保存记录、证据引用、当前判断和调查方案。判断应包含已知进展、未解问题、反证与限制，
不要求已经得到最终答案。普通 note 仍作为历史。Node 的 `plan` 是调查策略；Task 的
`next_action` 是唯一的下一步执行动作。`task_update(action="wait", wait=..., next_action=...)`
同时保存等待条件和唤醒后的动作，避免等待新 Job 却保留旧动作。

Brief 分别提供当前问题、显式 assessment、近期过程 notes 和待处理 Jobs。
普通 note 的 finding 是 `kind="note"`、`selected_assessment=false`；只有 `assessment_ref`
明确选中它时，后者才为 true。选中的其他历史记录使用 `kind="record"`，发布结果使用
`kind="result"`。新增 note 或 Job 完成不会自动发布 Result、替换判断或证明科学正确。

每个范围内 Node 最多提供 3 条近期过程 note，按不可变记录的 sequence 从新到旧选择。
被显式选为 assessment 的旧 note 可以另外作为当前判断展示，也计入 note 覆盖数量。
当前判断优先于过程 notes，不会仅因新增记录而被近期窗口挤掉。完整判断、限制与全部显式引用
作为一个整体纳入预算；放不下时使用 `content_omitted=true` 和确切读取入口，不保留可能丢失
数值或限定条件的半句话。goal 和 plan 放不下时通过 `omitted_fields` 标明。
模型在基于省略判断决策前必须读取原记录。`coverage.notes` 和 `coverage.omitted.notes`
显示纳入与省略的历史数量。通过 `research_read(ref=...)`
读取确切原记录，通过 `research_search(node_id=..., kind="note", limit=..., offset=...)`
分页获取完整历史和总数。

引用只能来自真实记录身份和显式引用字段，不能从 note 正文中猜测引用。
即使 note 写得很肯定或包含初步结论，它仍是过程记录，不能因此获得科学验证或发布状态。
缺少当前判断时给出 `current_assessment_missing` 提示。判断之后新增 Result 或 Job 终态、
收集完成记录时，给出 `new_evidence_after_assessment` 提示，要求核对相关性；不会自动替换
判断，也不会因记录时间较新就认定旧判断科学上失效。

## 选择与刷新

选择当前 Task 的焦点、事件涉及的节点、等待 Job 的节点和任务入口，再扩展直接的
`part_of`、`requires`、`alternative_to` 以及选定结论的引用关系。未绑定范围时最多选择
本会话创建的节点中最近活动的一个节点。完整证据仍通过 research_read、research_search 和 job_status 获取。

每次 generation 准备时，运行本地确定性读取，并比较范围和相关事实的指纹。
入口是 `apps/agent/runtime/setup.mjs` 的 `prepareContext` hook；已认证的输入事件引用
也会在没有顶层 Task 时传入选择器。筛选和摘取由 Python 完成，不调用模型决定读哪些记录。
范围包括任务身份、要求版本、入口、焦点、要求来源和等待 Job；事实包括候选节点与结果、
相关关系、诊断和 Job 状态，以及范围内全部普通 note 的身份与 sequence、各 Node 近期 3 条
note 的内容指纹。不会为了计算版本而加载全部历史 note 正文。
追加范围内普通 note 即使不改变 Node revision，也会刷新概览；无关 Node 的 note 不改变
显式范围的版本。受显示预算省略的候选记录同样参与版本判断。
首次进入、范围变化或相关事实变化才追加新的 pi.context，相同事实不重复注入。
输入来自用户、Job Manager 或 Task Controller 不影响这个判断。

读取通过 Pi memo 与 generation 截止位置一起固定；恢复复用固定结果。压缩只总结所选的历史，
不把最新研究状态倒填进旧摘要。正常恢复和压缩不单独要求重建概览。
读取失败会注入明确的不可用状态，同一输入内不反复重试；新输入可重试。

## 上下文状态

- availability：研究背景可用或不可用。
- projection_status：运行事件同步到研究记忆库是否完整，值为 complete / incomplete。

Task Controller 是否推进任务与概览是否刷新分开判断。Agent 通过研究工具读取证据、形成判断
并保存；上下文模块不调用第二个模型重新解释。数据同步不完整时直接呈现，不用生成摘要掩盖。
整体背景以 2,000 tokens 为软目标，出现矛盾时可到 4,000；最终请求仍受输入预算检查。

## 压缩与输入预算

研究概览只是上下文的一部分。Pi 管理对话历史、工具结果、压缩摘要和最近保留内容；
`beforeRequest` 附加当前任务控制信息，然后检查整个请求的估算大小。
输入预算取 `contextWindow - reserveTokens` 与可选 `maxInputTokens` 的较小值。
`reserveTokens` 是回答和请求开销的预留；它与研究概览的 2,000/4,000 token 软目标不同。
模型窗口、输出额度和部署上限的配置见[模型配置](MODEL_COMPATIBILITY.zh-CN.md)。

`prepareSummary` 只根据被压缩的历史生成补充说明和上下文锚点，不读取最新研究并倒填历史。
最终请求超预算时可要求 Pi 做一次阻塞压缩；仍无法满足预算时不会发出主模型请求。
窗口估算和输入预算由终端显示，详细计数可通过 `/usage` 查看。

## 单一合同

当前只接受 view="brief" 和 research-brief/1，旧 view="review" 与调用方指定的
trigger 不再接受。Task 的上下文指针记录实际注入版本，
不声称记录已经被科学审查。旧会话协议不自动翻译，不创建双接口或双写记录。
