# 存储与恢复

工作区 manifest 使用 `research_workspace/3`，Node 使用 `research-node/2`，用户 Task 使用 `coragent-user-task/6`。运行时、schema 与 Skill 必须同步部署；旧 Node/Task 格式没有兼容别名或并行读取路径。Node 的 plan 保存假设和当前调查，note 留存过程；Task 保留目标、条件、下一步、执行计划和控制，不再保存另一份科学计划。原始要求、研究修改和执行观察区分来源。Python 命名空间统一为 `research_agent.research`，没有并行 state 或全局 progress 协议。

Node 身份稳定，工作目录位于 `research/nodes/<node_id>/`。不可变 Result 固定它所对应的 Node 版本和实际依据。记录保存历史；索引、反向关系、工作区/Node Markdown 与预算内检索都是可重建视图。修改组织关系不移动目录。

`Node.assessment_ref` 选择同一 Node 的一条作者记录或 Result 作为当前研究判断。用 `research_update {node_id, note, references, as_assessment:true}` 保存带引用的新 note 并选定，需要修改 plan 时放在同一请求。note 的实际引用、被选记录编号和修订后的 Node 版本在同一事务中保存；读取冲突时均不提交。普通 note 只追加历史，不替换当前判断，也不递增 Node 版本。不要另建需要与这些记录同步的 progress 或 memory 文件。

`operations/` 保存运行时负责的派发、收集和投递回执。`artifacts/<id>/payload` 及 manifest 保存固定文件及来源。可变工作文件应先登记，再成为正式产出。Pi 保存会话历史；Memory 跨会话存在，但不替代会话记录。

受管研究数据经公开工具写入，工作文件用原生文件工具。事务保证一致更新，请求回执用于重试恢复。未知派发结果用原身份协调，不换 Job 重发；未知邮件投递由邮件回执处理，修改 Memory 不得触发重发。

旧工作区不支持、不迁移、不改写。新建工作区并显式导入材料。引用错误应读取现有对象，不自行编造 ID 或回退路径。

对象使用工作区内的正式编号，如 `node_1`、`result_1`、`art_1`，直接引用工具返回的 ID。读取材料使用 `artifact_id`，准备请求使用 `prepared_1`。编号不回收，内容哈希单独保留。

## 上下文与修订

`research_context` 是记录当时的观察；`runtime_control` 提供当前任务控制状态和真实用户 submission ID。即使用 user 角色承载，两者也不是新用户指令。Brief 可能省略对象或完整字段；用 `research_read`/`research_search` 读取当前记录。运行时任务控制可能缩短续接内容，此时用 `task_read` 读取完整任务。替换 Node 字段前完整读取；上下文与压缩摘要不构成读取回执。发生过期读取冲突时重新读取并合并。纠正 Result 使用 `supersedes`，随后复核受影响的结论和报告。关闭 Node 不等于科学验证通过或任务完成。

确定性 Brief 优先提供已选判断及其局限、证据引用，再补充近期 note；判断完整放入，放不下则要求读取，不静默拆开结论与限定条件，也不再调用第二个模型重组缺失内容。选定后出现新证据的提示要求复核，不自动否定或替换旧判断。具体续接行动只由 Task 的 `next_action` 维护，进入等待时与所等 Job ID 同时保存。

搜索使用 `kind`：例如 `research_search({"kind":"result"})` 查找已发布结果，`{"kind":"result_published"}` 查找发布记录。没有汇总所有记录的 `kind="record"`；需要按来源筛选时省略 kind，使用 origin=user/runtime/agent。`research_read({"ref":"<node_id>","field":"subjects"})` 读取节点的研究对象。read 分页按 Unicode 字符，search 分页按条目，artifact_read 分页按字节。
