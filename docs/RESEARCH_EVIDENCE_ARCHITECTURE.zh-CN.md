# 研究对象、执行证据与当前判断

Research Memory 保存研究过程和解释，不裁定科学真伪。Pi 继续负责 Agent 循环、工具调用及会话；这些能力不属于 Research Memory；已有工作区不会自动迁移。

## 对象与结论

Node 和 Result 的可选 `subjects` 将领域对象的不可变 Artifact/Result 引用命名为 target、calculated 等角色。引用只证明对象明确存在，不证明其内容正确；Node 与 Result 的角色由调用方明确提供。领域工具生成及对照结构身份，Memory 不读取 SMILES 或 Gaussian。

Chemical 的 inspect/seed 输出 `chemical-identity/1`，对规范异构 SMILES、电荷及 RDKit 版本生成身份摘要，原子编号不影响规范身份。`chemical.compare@1` 通过具名 target/actual 输入比较结构 JSON 或 XYZ。XYZ 必须给出实际电荷，键级推断方法明确写入结果；立体化学未确定时返回 indeterminate。比较范围不包含机理或能垒。

Result 的 observation 是记录的观察，conclusion 是作者解释，check_refs 引用具体检查材料或收集回执。验证回执中的状态由执行结果提供，不能通过发布 Result 的参数伪造一个 pass。检查失败或未确定不阻止保存研究判断。Artifact 类型的 check_ref 保留原始材料引用，不被 Memory 自动认证为验证器结论。

## 来源、解析和检查

执行器请求的 input_roles 记录每个输入角色的暂存路径和摘要，提交时与实际暂存声明核对。既有 Job 输入清单、资源摘要、环境观察、命令及不可变收集回执继续形成来源记录。验证器回执分别展示 execution_status、parsing、scientific_verdict（若验证器提供）和 provenance；来源验证不代表科学正确。

Gaussian 标题摘要是附加交叉检查。解析器支持已知标记的有界续行，包括历史 CoRAgentSpec，不对整份日志删除空白后匹配。缺失、无法读取和实际摘要不一致分别表达；原始证据保持不变。聚合 verdict 保留保守语义，scientific_verdict 另列已完成的科学条件检查，两者均注明范围。显式 Gaussian runner 的结果也分别记录执行、解析和请求检查状态。

Skill 指导 Agent 审查证据、记录缺口并选择下一步；某个自写验证器失败不构成禁止继续研究的通用门槛。原始材料缺失、引用不合法、暂存摘要不一致等工程约束仍严格检查。

## 统一受管 Python 入口

执行声明通过 module_paths 声明随 Job 暂存的导入目录，目录必须属于声明的资源闭包。准备器、提交校验和目标侧启动共同使用受摘要保护的 python_entrypoint.py。启动器只依赖标准库，独立于控制端包；设置入口与声明目录后运行脚本，加载失败返回结构化诊断。已登记的化学执行器和验证器均走此入口，新增声明可显式选择同样的方式。直接脚本调用必须使用已登记的分类路径。

CF22D doctor 在错误处理范围内加载依赖，区分依赖缺失与方法初始化失败。诊断不执行 SCF，普通测试无需调用真实模型或科学求解器。

## 修订与需复核提示

当前研究判断由 Node 的 `assessment_ref` 选定已有不可变记录，不增加独立进展对象。
`research_update` 接受 `references` 和 `as_assessment=true`：一次调用保存带明确引用的
note，并将其选为当前判断，可同时修订 plan。系统先检查读取依据，再将实际 note 编号、
修订后的 Node 快照、引用关系和计划作为一笔事务提交，Node 版本只递增一次。
引用允许已有 Node、Result、用户消息、作者记录、运行时记录、Job、收集回执和经验证
Artifact；正文出现编号不等于结构化引用。引用不存在或读取过期时不保存部分进展。
不选定的普通 note 保留过程，不改变当前判断或 Node 版本。

发布 Result 时，`as_assessment=true` 将保存新结果与选定当前综合判断作为一个原子修订。必须读过对应 Node 字段；读取冲突时两者均不保存，重新读取并判断后再重试。普通发布不修改当前判断；最新 Result 或 supersedes 关系都不自动选定综合判断。需要选定已有 Result 或同 Node 的作者记录时，使用 research_update.assessment_ref。supersedes 显式标记纠正对象，不改写历史记录。

`research_update.assessment_ref` 与 `as_assessment=true` 不能同时提供：前者选择已有记录，
后者选择本次新 note，均使用同一个判断字段。阶段性、负面和未定结论都是有效 Result，
无需等研究全部结束。解释一批结果、调整路线、等待或交付前，Agent 维护简短的当前判断，
同时保留已确立内容、未解决问题、仍有效的反证与限制，避免只记录最后一次 Job。

Node 的 plan 统一保存当前假设和调查思路，note 留存过程决策；Result 不接受 progress 参数。同一发现按用途记录为 note 或 Result，不要求重复写入两者或 Task 进展。执行事实与发布证据由现有工具追踪；具体下一步只由 Task 的 next_action 保存，进入等待时与所等 Job 同次更新，避免保留过期动作。Node 使用 research-node/2，Task 使用 coragent-user-task/6，运行时、合同和 Skill 必须同步升级，不保留旧字段别名或双协议。

新 Result 保存发布时的节点上下文摘要，已有 basis_refs 保留引用来源版本。读取 Result、当前判断卡片与生成的 Markdown 时派生需复核提示：节点上下文变化、引用结果被替代、外部节点来源版本变化。单独追加笔记不会替换当前综合判断，也不会据此判定旧结果错误；Brief 纳入近期 note 只用于恢复过程，不晋升为结论。

确定性 Brief 优先提供完整的已选当前判断及其证据引用、限制，近期 note 只作补充。
超出预算时保留编号与明确的读取要求，不截去半个数值或把限制从结论中剥离；不再使用
第二个模型综合已裁切内容。选定判断后出现新结果或相关终态 Job 时提示需要复核，
判断是否需要修改仍由研究 Agent 负责。研究恢复应能依靠这些持久记录，不依赖旧聊天
历史恰好仍在上下文中。

报告作为 Result 保存其 files 与 inputs/evidence_refs，使用相同的时间、来源和需复核机制；普通散落的 Markdown 文件不会被框架自动解析或重写。旧 Result 没有上下文摘要时不会伪造一个历史版本，只能根据已有引用发现替代关系。

## 验证

使用统一 tools/test/runner.py，在 local_debug 下进行确定性测试；不导入既有研究工作区的数据。回归覆盖位置异构体、原子重排、XYZ 推断、摘要折行与截断、解析失败、独立启动、真实本地比较 Job、输入角色摘要篡改、失败检查仍可发布、原子修订冲突及报告引用过期。研究连续性还检查带引用 note 的原子选定、会话读取依据、未知引用与过期读取无部分修改、中断重放、普通 note 不替换判断，以及无聊天历史时的恢复。全套验证同时检查生成协议、资源清单、原生 Pi、wheel 导入和服务清理。
