---
name: candidate-generation
description: 根据映射端点、反应坐标和结构证据构建并搜索过渡态与反应路径候选几何。
---

# 过渡态候选生成

[English version](SKILL.md)

## 脚本路由

按 executor ID 查看[操作入口](references/commands.zh-CN.md)，再读取本 Skill 中对应的输入与验证合同。普通调用不需要阅读源码；`scripts/` 中未列出的文件是内部辅助模块。

把反应假设转成可供 TS 或路径求解器搜索的几何时使用本 Skill。输入是一个有映射的基元步骤：反应物/产物或片段、键变化、电荷、多重度、相关构象，以及进攻方向、质子转移或立体化学证据。输出是带方法、约束、来源帧和下一项验证动作的候选集合。

## 方法选择经验

- **QST2**：映射的反应物和产物几何可靠、步骤近似单一平滑重排时使用；保持原子顺序、电荷和自旋一致。
- **QST3**：端点可靠但反应中心需要中间猜测时使用；提供显式映射的 TS 样几何，避免任意插值替你选择机理。
- **反应姿态 + 受限扫描**：分离片段、缔合、取代、环加成、质子转移或进攻方向不清楚时使用。生成多个面/距离，再用 `chemical.scan-xtb@1` 或 `chemical.scan-gaussian@1` 松弛成键/断键坐标。
- **松弛一维/二维扫描**：一两个距离、角或二面角控制事件且端点不足以定位势垒时使用；把高能或曲率改变的帧作为 TS 种子。
- **NEB**：两个端点极小点已知、路径包含多个耦合坐标时使用；用 `chemical.neb-xtb@2` 或 `chemical.neb-gaussian@2`，再把路径最高区域交给 TS 优化。
- **直接 TS 优化**：已有虚频方向、旧 TS、文献几何或可靠 QST/扫描帧时使用；用 `chemical.gaussian-input@1` 或 `chemical.cf22d@1` 的 TS 任务。
- **构象/姿态枚举**：扭转角、进攻面或片段取向是主要不确定性时，先用 CREST 或 `reactive-geometry`。

在 validation 或能量证据真正区分前，保留多个位点、进攻面、构象和机理假设。扫描极大值、NEB 图像和 QST 插值是候选/重启帧，经过 `validation` 后才可形成 TS 结论。

不要对未对齐端点的笛卡尔坐标直接取平均来构造 TS 猜测。先建立原子映射和共同坐标系；即使端点已对齐，中点也可能造成键坍缩或片段相互穿过。使用映射 QST 准备器或有依据的反应姿态/路径方法，再检查接触和片段几何后交给 Gaussian 精修。

## 推荐闭环

1. 明确原子映射、成键/断键、转移坐标和电子态。
2. 用 `chemical.path-candidates@1`（`chemical.qst-prepare@1`）准备相容端点，或提供 path specification。
3. 片段或进攻面不清楚时，用 `chemical.reactive-sites@1` 和 `chemical.reactive-pose@1` 生成/编辑反应姿态。
4. 运行扫描、梯度、QST 或 NEB，并检查收敛、反应中心距离和路径帧。
5. 路线失败后，使用收集到的 Attempt 诊断以及已核实的端点/几何上下文运行 `chemical.search-recovery@1`。只有列出的前置条件都满足时才执行 `auto_continue`；`needs_review` 必须先修订假设或修复输入。
6. 保留若干化学上不同的帧，附上来源 digest，交给 TS 优化和 `validation`。
7. 若搜索坍缩到极小点或出现畸变，根据失败几何改变姿态、坐标、端点或方法后再试。

## 已注册操作

`chemical.path-candidates@1`：映射 QST/路径输入；`chemical.qst-prepare@1`：QST2/QST3；`chemical.scan-xtb@1`、`chemical.scan-gaussian@1`：受限松弛扫描；`chemical.gradient-xtb@1`、`chemical.gradient-gaussian@1`：梯度/路径计算；`chemical.neb-xtb@2`、`chemical.neb-gaussian@2`：ASE NEB v2。
`chemical.search-recovery@1`：搜索失败后的证据驱动下一路线决策。

两个 QST 准备入口共用 `skills/chemical/_shared/gaussian_input.py` 的笛卡尔序列化器。生成后自动回读并核对电子态、元素顺序和坐标；向准备器提供显式原子映射，生成过程保留这一顺序。将生成的 `.gjf` 交给 `chemical.gaussian-input@1` 检查并准备，再用 `job_start` 提交其准备好的请求。

方法判据见 [candidate_generation.zh-CN.md](references/candidate_generation.zh-CN.md)，路径操作见 [path_search.zh-CN.md](references/path_search.zh-CN.md)，QST 和 NEB 细节见对应 reference。姿态构建使用 [reactive-geometry](../reactive-geometry/SKILL.zh-CN.md)，鞍点/IRC 证据使用 [validation](../validation/SKILL.zh-CN.md)。

## Further references

- [ase neb executor.zh CN](references/ase_neb_executor.zh-CN.md)
- [path preparation.zh CN](references/path_preparation.zh-CN.md)
- [reaction task interface.zh CN](references/reaction_task_interface.zh-CN.md)
- [script layout.zh CN](references/script_layout.zh-CN.md)

昂贵搜索前先读[方法选择](../method-selection/SKILL.zh-CN.md)，区分探索与精修。复用已验证结构和失败证据，用实际映射几何、二面角及立体化学去重，不能把文件名或随机初始结构当成不同构象。不要预设每个起始构象必须有独立反应 TS：区分构象转化到可反应盆地的路径与不同成键鞍点，候选先通过几何检查再精修。
