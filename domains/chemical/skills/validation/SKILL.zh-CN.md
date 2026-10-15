---
name: validation
description: 根据鞍点、目标振动模式、结构、电子态、立体化学和双向 IRC 连通性证据验证过渡态候选。
---

# CoRAgent 过渡态验证

[English version](SKILL.md)

使用本 Skill 判断候选结构能否作为可信的过渡态。候选生成提供候选结构；双向 IRC 连通性属于
验证维度，用于检查候选是否连接到已声明的反应物和产物势阱。

规范化证据可分别使用 `chemical.stationary-check@1`、`chemical.mode-check@1`、
`chemical.irc-check@1` 作通用独立检查；`chemical.gaussian-evidence@1` 转换指定原始日志
section。合同、调用示例、阈值和范围见[通用证据检查](references/general_checks.zh-CN.md)。
它们是 executor Job，不增加新的研究准入门槛。
使用 `chemical.path-irc@1` 从已验证的鞍点检查点准备有界正向和反向 IRC 输入，再用声明的
Gaussian 或其它有依据的后端执行并收集验证证据。
输入准备合同和来源要求见 [IRC 输入准备](references/irc_preparation.zh-CN.md)。
候选生成向 validation 交付的输入边界见[反应搜索任务接口](../candidate-generation/references/reaction_task_interface.zh-CN.md)。

核验优化与驻点证据、经典一阶鞍点所需的唯一相关虚频、沿所提反应坐标的位移、电荷与
多重度、电子态一致性、原子映射、几何和立体化学。必须检查原始输出和振动向量；正常
终止或单个负频本身不充分。

在研究笔记中明确检查标准、支持证据、未解决问题和下一步，引用实际收集的材料。计算完成不能代替对科学结论的判断。

鞍点与振动模式证据见
[transition_state_validation.zh-CN.md](references/transition_state_validation.zh-CN.md)，路径
计算后的盆地身份判据见
[connectivity_validation.zh-CN.md](references/connectivity_validation.zh-CN.md)，映射、对齐
与立体化学比较见 [structure_validation.zh-CN.md](references/structure_validation.zh-CN.md)。


注册验证器：调用 `job_start`，提供 `validator_id="chemical.gaussian_frequency"`、新的 `request_id` 和 `input_artifact_ids=[已收集的 parsed.json Artifact ID]`。验证器版本为 `1`。运行时记录实际执行及输入摘要。它仅检查正常结束和恰好一个负频率；振动模式性质、几何与 IRC 连通性仍须分别验证。

按当前反应假设定义成键、断键、原子迁移或其他相关坐标。已收集的原始输出可以交给
适用的分析脚本或上述独立检查通过 Job 验证；不要求先注册特定反应的验证器。
选用随包的[专用路径验证器](../candidate-generation/references/gaussian_path.zh-CN.md)前，
先核对其拓扑和输入范围；不能把该专用路径的判据当成通用过渡态定义。

尤其是 `chemical.reaction_mapping`、`chemical.gaussian_saddle` 和
`chemical.gaussian_irc_connectivity` 的版本 1，名称虽通用，实际使用 DA 契约。
其它变换返回未评估的适用范围，不代表反应失败，详见[能力清单](../method-selection/references/capabilities.zh-CN.md)。

检查提供有限范围的证据，不是通用研究门禁。区分工具执行失败、材料无法解析和已完成检查但条件不满足。parsing.status、scientific_verdict（若提供）与回执 provenance 分别表达这些状态。Job 输入输出摘要证明记录的来源；求解器标题标记只是附加核对。证据未确定不禁止有理由的后续实验，但需要明确记录不确定性，不声称检查通过。

Gaussian 专用检查参考由本 Skill 负责，见 [gaussian_validation.zh-CN.md](references/gaussian_validation.zh-CN.md)。

对每个 IRC 方向保留来源鞍点、方向、路径 Artifact、端点 Artifact 与摘要。检查起始几何与已验证
鞍点一致、程序终止、路径完整性、最终几何及可用时的最终梯度。将每个端点与显式选择的反应物
或产物 Artifact 比较，核验 mapping、电荷、电子态、成断键、关键内坐标、构象和立体化学。
详细判据见 [IRC 验证](references/irc_validation.zh-CN.md)；部分路径和未确定的端点身份都应保留为未解决证据。
