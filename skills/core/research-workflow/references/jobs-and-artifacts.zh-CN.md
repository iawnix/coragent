# Job 与材料流程

生成文件目录是工作流约定，不新增原生工具限制。`research_create` 和 Node `research_read` 返回绝对 `work_dir`，用于可修改的结构、脚本、临时文件和请求 JSON。未关联 Node 时使用工作区内的 `research/work/`；报告放在 `reports/`。优先指定绝对输出路径，也可以在生成命令开头使用 `cd -- "<返回的 work_dir>" && ...`，正确引用实际路径；未关联的工作目录如不存在则先创建。此时 `--output prepared/request.json` 与相对输入路径从该命令的 cwd 解析。`work_dir` 不是 bash 参数，不要假设一次 cd 会延续到后续调用或改变 read/write/edit 的路径解析。普通读取、搜索和不生成文件的诊断无需切换目录。

原始输入保留在 `inputs/`，保留运行时管理的 Job/Artifact 文件，不移动历史请求和证据。避免在工作区根目录散落生成文件。SSH 或远程 Job 使用配置的远程工作、scratch 目录或用户指定目标，本地 `work_dir` 不能当作远程路径。scp/rsync 应区分本地与远程两端，本地下载和重定向输出放入本地草稿或报告目录。这些约定指导 agent 选择文件位置，不增加文件系统隔离，也不改变已有工具权限。

按已安装领域 Skill 准备请求，把返回的 request_file 和 request_sha256 交给 job_start；用 node_id 明确研究归属。其它执行字段已固定在请求文件中。直接 argv 提交需声明实际输入、输出和 execution_target。准备与诊断允许不关联 Node。

自定义科学脚本通过配置的执行准备入口使用 `--script <file.py> --backend <binding>`。直接 argv 提交不会选择科学 Python 或软件后端。准备请求和报告排版使用原生工具，科学计算使用受管 Job。

适配层在提交时固定 Node 版本和实际输入；后来修改方案不改变旧 Job 检验的内容。Job Manager 是派发和终止事实的来源。job_status 查看、job_cancel 请求取消、job_reconcile 协调不确定性、job_collect 保存输出和来源，重复收集不会重新执行。

artifact_create 保存新文本，artifact_register 导入文件，artifact_read 有界读取。科学 Job 的输出通过收集保留生产身份；分析请求声明并暂存实际输入；验证器作为普通 Job 运行。读过文件不自动成为科学证据使用。

下面的工具调用顺序使用占位符，实际调用时替换为返回值：

1. 通过 bash 使用所选 executor 和 `--output prepared/request.json` 准备请求并检查内容。返回的 `request_file` 和 `request_sha256` 描述待提交工作，此时尚未执行科学计算。准备失败时先修正参数。科学计算无论预计耗时长短，都通过 Job 执行。
2. `job_start({"node_id":"<node_id>","request_file":"<request_file>","request_sha256":"<request_sha256>"})`。不要添加请求中已固定的执行字段；需要修改时重新准备。`prepared_ref` 可以替代文件与摘要组合，不能同时传。Job 的 `timeout_seconds` 控制计算时限，bash 的 timeout 控制准备时限。
3. `job_status({"job_id":"<job_start 返回的 job_id>"})` 查看执行状态，不收集文件，也不确认科学有效性。继续使用同一 Job ID，直到执行结束。实际返回的监控 event_id 也可用于选择对应 Job。
4. `job_collect({"job_id":"<同一 job_id>"})` 保存可用产物与日志，包括失败 Job 的输出。检查 output_validation 和 result_receipt.collection_state，部分收集不等于完整证据。使用 `artifact_read({"artifact_id":"<所选 artifacts 条目的 artifact_id>"})` 或其返回的 artifact_ref 读取相关材料。
5. 检查实际输出后发布：`research_result({"node_id":"<node_id>","conclusion":"<有依据的结论及局限>","evidence_refs":["<job_id>","<result_receipt.receipt_id>"],"files":[{"name":"<产物名称>","artifact_ref":"<所选 artifacts 条目的 artifact_ref>"}]})`。特定检查的回执也可以放入 check_refs。inputs 只填写实际采用的固定 Result/Artifact；Job ID 或回执不能作为结果输入或文件附件。

撰写报告时，用 artifact_create 的 name 和实际文本 content 创建材料；导入已有文件时，用 artifact_register 的工作区文件 path。两者都会返回 artifact_id 和 artifact_ref，但登记本身不证明计算已执行。不要把 Job 原始输出重写成文本或去掉生产来源后登记，以绕过 job_collect。artifact_read 的 offset/limit 以字节计，继续读取时使用 next_offset。

research_update 用 node_id 与 note 解释变化；有可引用产出时，research_result 用 node_id 与 conclusion 发布。结果文件引用已登记 artifact_ref。工作目录保存可修改草稿，正式结果关联固定材料。调用 Job 或原生文件工具前不需要研究生命周期转换。

有意重复完全相同的计算时，用新的 work_id 准备请求，并提交包含匹配 predecessor_job_id、reason、budget 的 repeat。复用请求身份会复用 Job；duplicate_execution 通常应转为查询或收集返回的 Job。验证器 Job 必须使用已登记的 validator_id/version，并按输入角色规定的数量、顺序传 Artifact；collected_output 角色要求生产 Job 当前已收集的证据。job_probe 检查 execution target 基础设施，不验证科学软件；job_reconcile 恢复已有执行状态，不重新提交；job_cancel 后检查返回状态，unknown 不等于已经停止。

每次计算在准备阶段通过 `--` 之前的 `--cpus`、`--job-memory-mb` 指定资源。配置值是默认值，不是上限。调整申请需重新准备，不要修改已固定请求，也不要因默认值较小而判定必须管理员扩容。容量、可用性和排队由所选执行目标的运行时或调度器处理。见[逐作业资源](../../../../docs/EXTERNAL_JOBS.zh-CN.md#逐作业资源)。

发布结论的引用选择与修订见[研究证据](../../research-memory/references/evidence.zh-CN.md)，任务等待和取消见[任务生命周期](task-lifecycle.zh-CN.md)。
