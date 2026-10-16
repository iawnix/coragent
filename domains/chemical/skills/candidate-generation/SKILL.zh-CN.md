---
name: candidate-generation
description: 根据映射端点、键变化、约束和已有结构证据，为过渡态与反应路径搜索生成候选几何。
---

# CoRAgent 过渡态候选生成

[English version](SKILL.md)

使用本 Skill 为所提出的基元步骤生成候选几何。候选生成不能证明其为过渡态；验证由
`validation` 负责，方法与 Backend 选择由 `method-selection` 负责。
本 Skill 属于科学搜索操作层。Gaussian、xTB 等软件配方仍属于后端适配；此处提到它们
只是为了说明如何通过既有 Job 接口执行搜索。

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
方法的前提。Gaussian QST/TS 输入见 [Gaussian Skill](../gaussian/SKILL.zh-CN.md)。

[映射路径准备器](references/path_preparation.zh-CN.md) 接收显式键变化，支持单片段端点
自动构象生成或用户提供的映射几何，通过已有 Job 配方生成 QST2 输入。
可选几何策略不决定科学验收结论，使用前核对输入与验证范围。准备器不支持某种输入
不等于研究方法不可用；其他方法仍可使用共享 runner、显式求解器输入或任务脚本。
方法判据见 [candidate_generation.zh-CN.md](references/candidate_generation.zh-CN.md)，
NEB 可用性与前提见 [ase_neb_executor.zh-CN.md](references/ase_neb_executor.zh-CN.md)。
把候选交给 IRC 或 validation 时，使用统一的[反应搜索任务接口](references/reaction_task_interface.zh-CN.md)。

脚本职责和分类路径见 [脚本布局](references/script_layout.zh-CN.md)。只有使用可选的
路径准备器时，才需要阅读其专用说明。

阅读[专用路径准备](references/gaussian_path.zh-CN.md)；
其中的局部契约不定义候选生成整体的适用范围。候选应交给 `validation` 获取鞍点证据和双向
IRC 连通性验证；验证准备 IRC 输入时仍须保留端点和求解器元数据。

已有材料端点的 QST2/QST3 使用 `chemical.qst-prepare@1`；有界一维/二维扫描使用
`chemical.scan-xtb@1` 或 `chemical.scan-gaussian@1`；xTB 梯度与 NEB 使用
`chemical.gradient-xtb@1`、`chemical.neb-xtb@2`。输入合同、可选路径环境绑定、
续算规则及 calculator 实际边界见[材料路径操作](references/path_search.zh-CN.md)。

基态自旋 Gaussian 梯度与 NEB 另有 chemical.gradient-gaussian@1、chemical.neb-gaussian@2，
独立电子设置与范围见[路径操作](references/path_search.zh-CN.md)。

新 xTB/Gaussian 路径搜索使用 [ASE NEB v2](references/ase_neb_executor.zh-CN.md)。失败或畸变时按[搜索恢复](../method-selection/references/search_recovery.zh-CN.md)诊断，结合[局部几何](../chemical-input/references/local_diagnostics.zh-CN.md)和[轨迹](../report/references/research_tools.zh-CN.md)选择重启帧。
