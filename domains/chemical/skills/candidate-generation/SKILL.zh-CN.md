---
name: candidate-generation
description: 通过化学构造、扫描、QST、NEB 或构象与取向采样生成过渡态候选几何。
---

# CoRAgent 过渡态候选生成

[English version](SKILL.md)

使用本 Skill 为所提出的基元步骤生成候选几何。候选生成不能证明其为过渡态；验证由
`validation` 负责，方法与 Backend 选择由 `method-selection` 负责。

从明确的反应物/产物身份、原子映射、电荷、多重度与相关构象出发。根据成键变化和
已有证据选择化学构造、松弛扫描、QST2/QST3、直接 TS 优化、NEB 或片段取向采样。
所有种子和生成结构都应作为研究 Node 所属 Artifact 保存，并保留方法、约束、帧选择和来源。

已有候选因取向、反应中心距离或上一轮路径/振动证据而需要修正时，先使用
[reactive-geometry](../reactive-geometry/SKILL.zh-CN.md) Skill 生成带来源记录的反应构象候选，再交给 QST、扫描或 NEB。

不要把扫描极大值、NEB 图像、插值结构或受限结构当作已验证鞍点。候选结构本身可记录
为事实；失败或畸变的搜索只有在影响研究问题时才记录为研究记录。

用映射端点、键变化及相关坐标或约束表达所提出的步骤，再据此选择候选生成方法。
反应名称不决定必须调用哪个脚本或验证器；新增反应类型不要求新增工具或 Skill 分支。
通过现有 Job 接口运行显式求解器输入或有界任务脚本，保留原子对应关系，并核验所选
方法的前提。Gaussian QST/TS 和 IRC 输入见 [Gaussian Skill](../gaussian/SKILL.zh-CN.md)。

[映射路径准备器](references/path_preparation.zh-CN.md) 接收显式键变化，支持单片段端点
自动构象生成或用户提供的映射几何，通过已有 Job 配方生成 QST2 与双向 IRC 输入。
可选几何策略不决定科学验收结论，使用前核对输入与验证范围。准备器不支持某种输入
不等于研究方法不可用；其他方法仍可使用共享 runner、显式求解器输入或任务脚本。
方法判据见 [candidate_generation.zh-CN.md](references/candidate_generation.zh-CN.md)，
NEB 可用性与前提见 [ase_neb_executor.zh-CN.md](references/ase_neb_executor.zh-CN.md)。

checkpoint、原子映射与 IRC 输入约定见 [Gaussian 路径准备](references/gaussian_path.zh-CN.md)。

内置 DA 路线只支持六个中性、非芳香碳反应中心。芳香、带电或杂原子中心超出适用范围时属于未评估，不是对反应的反证。RDKit 读取 Kekule SMILES 会重新识别芳香性，重写同一分子不能扩展封装能力。改用显式键变化检查和独立准备的候选，或其它有依据的方法。生成的 IRC 输入用 CalcFC 在 checkpoint 几何上重算 Hessian，预算应包含这项成本。

已有材料端点的 QST2/QST3 使用 `chemical.qst-prepare@1`；有界一维/二维扫描使用
`chemical.scan-xtb@1` 或 `chemical.scan-gaussian@1`；xTB 梯度与 NEB 使用
`chemical.gradient-xtb@1`、`chemical.neb-xtb@2`。输入合同、可选路径环境绑定、
续算规则及 calculator 实际边界见[材料路径操作](references/path_search.zh-CN.md)。

基态自旋 Gaussian 梯度与 NEB 另有 chemical.gradient-gaussian@1、chemical.neb-gaussian@2，
独立电子设置与范围见[路径操作](references/path_search.zh-CN.md)。

新 xTB/Gaussian 路径搜索使用 [ASE NEB v2](references/ase_neb_executor.zh-CN.md)。失败或畸变时按[搜索恢复](../method-selection/references/search_recovery.zh-CN.md)诊断，结合[局部几何](../chemical-input/references/local_diagnostics.zh-CN.md)和[轨迹](../report/references/research_tools.zh-CN.md)选择重启帧。
