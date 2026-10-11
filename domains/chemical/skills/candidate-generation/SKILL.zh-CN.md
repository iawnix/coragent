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
