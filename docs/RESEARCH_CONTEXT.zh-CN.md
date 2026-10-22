# 研究上下文

Research Memory 是持久研究记录。Research Context 是 Agent Runtime 内部的上下文准备模块，
通过唯一的 `research_read(view="brief")` 接口读取 `research-brief/1` 研究概览。
概览是程序筛选和摘取的结果，模型可附加 Research Synthesis（研究综合摘要）；两者都不代表科学评估。

## 选择与刷新

选择当前 Task 的焦点、事件涉及的节点、等待 Job 的节点和任务入口，再扩展直接的
`part_of`、`requires`、`alternative_to` 以及选定结论的引用关系。未绑定范围时最多选择
本会话创建的节点中最近活动的一个节点。完整证据仍通过 research_read、research_search 和 job_status 获取。

每次 generation 准备时，运行本地确定性读取，并比较范围和相关事实的指纹。
入口是 `apps/agent/pi/setup.mjs` 的 `prepareContext` hook；已认证的输入事件引用
也会在没有顶层 Task 时传入选择器。筛选和摘取由 Python 完成，不调用模型决定读哪些记录。
范围包括任务身份、要求版本、入口、焦点、要求来源和等待 Job；事实包括候选节点与结果、
相关关系、诊断和 Job 状态。省略的候选记录也参与版本判断，无关研究的活动不改变该版本。
首次进入、范围变化或相关事实变化才追加新的 pi.context，相同事实不重复注入。
输入来自用户、Job Manager 或 Task Controller 不影响这个判断。

读取通过 Pi memo 与 generation 截止位置一起固定；恢复复用固定结果。压缩只总结所选的历史，
不把最新研究状态倒填进旧摘要。正常恢复和压缩不单独要求重建概览。
读取失败会注入明确的不可用状态，同一输入内不反复重试；新输入可重试。

## 三种独立状态

- availability：研究背景可用或不可用。
- projection_status：运行事件同步到研究记忆库是否完整，值为 complete / incomplete。
- synthesis_status：模型补充摘要为 not_requested / ready / failed。

取消 review_pending 和含义混合的 Review 生命周期。Task Controller 是否推进用户任务，
与研究概览是否刷新、模型摘要是否成功分开判断。
数据同步不完整时不请求模型摘要，避免用文本生成掩盖同步错误。

概览包含结果、终态或异常 Job、矛盾时，可调用模型对已经筛选的概览做无工具综合。
摘要输出最多 700 tokens，按具体概览指纹缓存；引用必须来自概览。
失败保留确定性概览，不阻止 Agent 读取原始证据。模型摘要不会写入 Research Memory。
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
trigger 不再接受。Task 的上下文指针属于 coragent-user-task/3，记录实际注入版本，
不声称记录已经被科学审查。旧会话协议不自动翻译，不创建双接口或双写记录。
