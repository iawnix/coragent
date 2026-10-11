# Job 与材料流程

生成文件目录是工作流约定，不新增原生工具限制。`research_create` 和 Node `research_read` 返回绝对 `work_dir`，用于可修改的结构、脚本、临时文件和请求 JSON。未关联 Node 时使用工作区内的 `research/work/`；报告放在 `reports/`。优先指定绝对输出路径，也可以在生成命令开头使用 `cd -- "<返回的 work_dir>" && ...`，正确引用实际路径；未关联的工作目录如不存在则先创建。此时 `--output prepared/request.json` 与相对输入路径从该命令的 cwd 解析。`work_dir` 不是 bash 参数，不要假设一次 cd 会延续到后续调用或改变 read/write/edit 的路径解析。普通读取、搜索和不生成文件的诊断无需切换目录。

原始输入保留在 `inputs/`，保留运行时管理的 Job/Artifact 文件，不移动历史请求和证据。避免在工作区根目录散落生成文件。SSH 或远程 Job 使用配置的远程工作、scratch 目录或用户指定目标，本地 `work_dir` 不能当作远程路径。scp/rsync 应区分本地与远程两端，本地下载和重定向输出放入本地草稿或报告目录。这些约定指导 agent 选择文件位置，不增加文件系统隔离，也不改变已有工具权限。

按已安装领域 Skill 准备请求，把返回的 request_file 和 request_sha256 交给 job_start；用 node_id 明确研究归属。其它执行字段已固定在请求文件中。直接 argv 提交需声明实际输入、输出和平台。准备与诊断允许不关联 Node。

适配层在提交时固定 Node 版本和实际输入；后来修改方案不改变旧 Job 检验的内容。Job Runtime 是派发和终止事实的来源。job_status 查看、job_cancel 请求取消、job_reconcile 协调不确定性、job_collect 保存输出和来源，重复收集不会重新执行。

artifact_create 保存新文本，artifact_register 导入文件，artifact_read 有界读取。科学 Job 的输出通过收集保留生产身份；分析请求声明并暂存实际输入；验证器作为普通 Job 运行。读过文件不自动成为科学证据使用。

下面的工具调用顺序使用占位符，实际调用时替换为返回值：

1. 通过 bash 使用所选 executor 和 `--output prepared/request.json` 准备请求并检查内容。返回的 `request_file` 和 `request_sha256` 描述待提交工作，此时尚未执行科学计算。准备失败时先修正参数。科学计算无论预计耗时长短，都通过 Job 执行。
2. `job_start({"node_id":"<node_id>","request_file":"<request_file>","request_sha256":"<request_sha256>"})`。不要添加请求中已固定的执行字段；需要修改时重新准备。`prepared_ref` 可以替代文件与摘要组合，不能同时传。Job 的 `timeout_seconds` 控制计算时限，bash 的 timeout 控制准备时限。
3. `job_status({"job_id":"<job_start 返回的 job_id>"})` 查看执行状态，不收集文件，也不确认科学有效性。继续使用同一 Job ID，直到执行结束。实际返回的监控 event_id 也可用于选择对应 Job。
4. `job_collect({"job_id":"<同一 job_id>"})` 保存可用产物与日志，包括失败 Job 的输出。检查 output_validation 和 result_receipt.collection_state，部分收集不等于完整证据。使用 `artifact_read({"artifact_id":"<所选 artifacts 条目的 artifact_id>"})` 或其返回的 artifact_ref 读取相关材料。
5. 检查实际输出后发布：`research_result({"node_id":"<node_id>","conclusion":"<有依据的结论及局限>","evidence_refs":["<job_id>","<result_receipt.receipt_id>"],"files":[{"name":"<产物名称>","artifact_ref":"<所选 artifacts 条目的 artifact_ref>"}]})`。特定检查的回执也可以放入 check_refs。inputs 只填写实际采用的固定 Result/Artifact；Job ID 或回执不能作为结果输入或文件附件。

撰写报告时，用 artifact_create 的 name 和实际文本 content 创建材料；导入已有文件时，用 artifact_register 的工作区文件 path。两者都会返回 artifact_id 和 artifact_ref，但登记本身不证明计算已执行。不要把 Job 原始输出重写成文本或去掉生产来源后登记，以绕过 job_collect。artifact_read 的 offset/limit 以字节计，继续读取时使用 next_offset。

research_update 用 node_id 与 note 解释变化；有可引用产出时，research_result 用 node_id 与 conclusion 发布。结果文件引用已登记 artifact_ref。工作目录保存可修改草稿，正式结果关联固定材料。调用 Job 或原生文件工具前不需要研究生命周期转换。

按用途选择引用字段，并使用实际返回的完整 ID：

| 字段 | 用途与允许的引用 |
| --- | --- |
| research_create.source_refs | 原始用户需求；只接受 user_* 消息。 |
| research_create.input_refs | 背景引用；接受已有 Node、Result、用户消息、笔记、运行时记录、Job、收集回执和已验证 Artifact。 |
| research_result.inputs | 推导结论实际使用的固定材料；只接受已有 Result 和已验证 Artifact。没有此类输入时省略。 |
| research_result.evidence_refs | 支持性引用；允许类型与 Node 的 input_refs 相同，包括用户消息和执行记录。需求来源不等于科学证明。 |
| research_result.files[].artifact_ref | 交付文件；必须是已验证 Artifact 引用，不能是可修改路径、Job ID 或回执。 |
| research_result.check_refs | 特定检查的依据；接受已验证 Artifact 或收集回执，不接受 Job ID。允许检查未得出确定结论。 |
| create/update/result 的 subjects | 命名角色；值只接受已有 Result 或已验证 Artifact。 |
| research_update.assessment_ref | 同一 Node 下已有的 Result 或由 Agent 撰写的笔记/记录。 |
| research_result.supersedes | 同一 Node 下需要明确修正的旧 Result。 |

根据用户请求解析出候选结构时，可在 evidence_refs 中引用结构 Artifact 和原始用户消息。不要把用户消息放进 inputs。例如（将所有示例 ID 替换为实际返回的引用）：

```json
{"node_id":"node_...","conclusion":"已解析出候选结构，反应机理仍未确定。","evidence_refs":["art_...","user_..."]}
```

搜索使用 `kind`：例如 `research_search({"kind":"result"})` 查找已发布结果，`{"kind":"result_published"}` 查找发布记录。没有汇总所有记录的 `kind="record"`；需要按来源筛选时省略 kind，使用 origin=user/runtime/agent。`research_read({"ref":"<node_id>","field":"subjects"})` 读取节点的研究对象。read 分页按 Unicode 字符，search 分页按条目，artifact_read 分页按字节。

研究文本长度统一按 Unicode 码点计算，不按 UTF-8 字节：goal 8000，title 1000，proposal/plan/progress 16000，note/conclusion/observation 64000，summary 4000，limitations 32000，关系 reason 4000，文件 name 1000、purpose 16000。组合字符中的附加符号分别计数。工具输出仍受字节预算限制，较大结果需分页读取。

任务工具使用实际用户提交 ID 的十进制字符串，与研究记录的 user_* 引用不同。通过 task_read 获取当前任务版本，不要把 Node 的版本填入 expected_revision。task_update 只接受对应 action 的字段，reason 可附于任意 action：

| action | 必填字段与含义 |
| --- | --- |
| refine | source_submission_ids 必须来自实际用户请求；可替换 objective 或 criteria。 |
| progress | evidence_refs；引用实际采用的 Result/Artifact 或当前任务的 Job。笔记本身不重置无进展计数，此处不接受收集回执 ID。 |
| wait | wait 中填写当前任务的 job_ids 和 all/any 模式。未知执行结果会唤醒任务以协调状态。 |
| block | reason 说明阻塞原因。 |
| propose_completion | completion 覆盖全部 criterion_id，每项至少有固定 Result 或 Artifact 支持；之后仍需交付最终答复。 |
| set_research | research 包含完整 entry_node_ids、focus_node_ids 数组；两者整体替换，[] 表示清空。 |

有意重复完全相同的计算时，用新的 work_id 准备请求，并提交包含匹配 predecessor_job_id、reason、budget 的 repeat。复用请求身份会复用 Job；duplicate_execution 通常应转为查询或收集返回的 Job。验证器 Job 必须使用已登记的 validator_id/version，并按输入角色规定的数量、顺序传 Artifact；collected_output 角色要求生产 Job 当前已收集的证据。job_probe 检查平台基础设施，不验证科学软件；job_reconcile 恢复已有执行状态，不重新提交；job_cancel 后检查返回状态，unknown 不等于已经停止。
