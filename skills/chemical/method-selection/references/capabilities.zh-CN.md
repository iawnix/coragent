# 当前化学能力与边界

[English](capabilities.md)。本表对应随包执行目录，不证明当前本地或远端软件已就绪，也不证明真实求解器的搜索成功率。先分清程序能力、项目执行/解析范围和目标环境，再选择方法。平台探测、环境检查、合成日志测试和真实科学验证分别提供不同证据。

## 独立操作

| 方法/操作 | 项目入口与实现 | 范围与缺口 |
| --- | --- | --- |
| 原始结构材料 | `chemical.material` | 保留 name/SMILES/XYZ、片段、未知设置与态声明，支持显式行置换及逆置换；不推断 XYZ 图、不认证态、不搜索反应映射 |
| 名称解析与候选检查 | `chemical.resolve`、`chemical.resolve-candidates` | PubChem/OPSIN 与有来源的 Agent 候选；查询失败可继续推断，不等于结构已确认 |
| 分子图与几何种子 | `chemical.inspect`、`chemical.seed` | SMILES 图、立体化学和显式 H 几何；生成种子不等于优化或充分构象搜索 |
| 映射核验 | `chemical.reaction` | 检查显式原子对应、守恒和声明键变化；不自动证明原子轨迹或发现机理 |
| 映射候选 | `chemical.map-candidates` | 显式图上的有界元素/同位素对应；identity 或最小键编辑 reaction 模式，保留歧义与截断，不推断机理 |
| 构象比较 | `chemical.conformer-compare` | 给定几何、图对称性、纯旋转及可选内部坐标；复合物整体对齐，映射覆盖有界，态声明单独比较 |
| 张量顺序 | `chemical.reorder-tensors` | 保留 ID/单位的 Cartesian 坐标、梯度、Hessian、模式可逆置换；不做空间旋转、质量加权或单位转换 |
| 结构身份比较 | `chemical.compare` | 分子图、电荷、同位素和指定立体化学；XYZ 键级为推断；不是完整构象/电子态比较 |
| 驻点/模式/IRC 检查 | `chemical.stationary-check`、`chemical.mode-check`、`chemical.irc-check` | 无约束、ground 态单势能面的规范化证据独立检查；保留小负频、路径截断与端点构象歧义；不证明波函数连续性或机理唯一性 |
| Gaussian 证据转换 | `chemical.gaussian-evidence` | 当前 HF/DFT SCF 范围内，将原始指定 section 转为绑定材料的驻点/IRC 证据；约束需声明，显式同位素质量未评估，不虚构端点极小点 |
| xTB 单点与优化 | `chemical.xtb` | 内置 GFN2-xTB 的 sp/opt/opt-sp；Hessian/MD 使用通用 Job，有界扫描/梯度/NEB 使用下方独立入口 |
| Gaussian 单点与优化 | `chemical.gaussian` | XYZ 的 sp/opt/opt-sp；能量解释受下述 HF/DFT SCF 解析边界限制 |
| Gaussian TS、频率、QST、IRC、扫描 | `chemical.gaussian-input` | 显式 GJF 执行及有限检查；不能从正常终止或虚频数直接认定目标路径；无完整扫描验收器 |
| CF22D | `chemical.cf22d`、`chemical.cf22d-doctor` | PySCF 的 sp/opt/opt-sp/ts/freq/thermo/opt_freq/ts_freq 及环境诊断；已有 RRHO，不包含 IRC、NEB、交叉点 |
| 映射端点与 TS 验证 IRC 输入 | `chemical.path-candidates`、`chemical.path-irc` | 候选端点准备和鞍点验证后的 IRC 输入准备；通用显式变换、相容单片段自动嵌入或给定映射端点；准备输入不执行 Gaussian |
| CREST 构象集合 | `chemical.crest`、`chemical.crest-ensemble`、`chemical.ensemble-select` | 有界 3.0.2 GFN1/GFN2 基态搜索、主要证据核验、身份推断与几何/电子能筛选；保留部分结果，不认证穷尽或自由能 |
| 复合物排布 | `chemical.complex-sample` | 有种子的刚性片段组装/扰动、碰撞与距离检查、原子来源；需要已有坐标，总自旋可保持未知，不进行优化 |
| 材料 QST2/QST3 | `chemical.qst-prepare` | 已有映射端点/猜测、相容态声明、置换与 GJF 导出；不认证极小点或基元步骤 |
| 弛豫扫描网格 | `chemical.scan-xtb`、`chemical.scan-gaussian` | 有界独立点一维/二维网格、原生约束、实际偏差、物理能量、失败记录和终止结果续算；不自动证明路径连续 |
| 梯度与 NEB | `chemical.gradient-xtb`、`chemical.neb-xtb` | xTB 6.7.1 GFN1/GFN2 梯度、单位/符号核对、v2 为 ASE 改进切向/爬山 NEB 与 FIRE/BFGS；保留部分路径和求值预算 |
| 能量分析 | `chemical.thermochemistry`、`chemical.ensemble-free-energy`、`chemical.energy-profile`、`chemical.scan-slice` | 基态来源组合、标准态、仅熵低频下限、有限构象 G、守恒计量能量差及成功扫描点；动力学另见后续条目 |
| 路径审计 | `chemical.pathway-check` | 明确假设、原子/计量/共享中间体连续性、缺步骤及可选经典模式/IRC 重算；不自动穷尽机制 |
| 条件动力学 | `chemical.tst`、`chemical.branching`、`chemical.kinetic-network` | 经典 TST、共同前体初始分支及带守恒/误差检查的封闭质量作用积分；不保证刚性网络求解 |
| Gaussian 电子态 | `chemical.electronic-gaussian`、`chemical.state-tracking` | 基态自旋 HF/DFT、单重 TDDFT/TDHF/TDA 单点/优化；目标能量/梯度/自旋解析；AO 特征重叠需提供密度/跨帧度量 |
| Gaussian 梯度/NEB | `chemical.gradient-gaussian`、`chemical.neb-gaussian` | 气相基态自旋梯度 calculator；使用 ASE NEB v2，不自动证明波函数分支 |
| 不同自旋交叉 | `chemical.mecp-gaussian`、`chemical.crossing-check` | 投影局部搜索及独立能隙/梯度/可选交叉缝 Hessian 检查；不提供全局 MECP、SOC、同自旋 CI 或非绝热动力学；不是 QBICS |
| 局部结构诊断 | `chemical.local-diagnostics` | 显式局部坐标、短接触、全局/中心纯旋转对齐；不判断键或电子态 |
| 结构图与报告 | `chemical.render`、`chemical.trajectory`、`chemical.research-report` | 固定视角轨迹/模式示意、坐标剖面和有来源的图文报告；明确作者解释与未完整路径 |

NEB 统一使用 ASE 版本 `2`，旧版本 `1` 入口已删除；其余上述入口为版本 `1`；实际参数与依赖见相应 Skill、CLI 和执行目录。上表不是工具白名单；未封装的方法可通过有依据、已核实的原生命令或任务脚本执行。单分子单点/优化不需要构造 R/P、映射或 TS。

## 验证器的真实适用范围

| 已注册验证器 / profile | 实际范围 |
| --- | --- |
| `chemical.gaussian_frequency@1` | 正常终止及有限频率表中恰好一个负频率；不检查模式归属、完整驻点或 IRC 身份 |

用 `chemical.stationary-check`、`chemical.mode-check` 和 `chemical.irc-check` 核对当前假设与计算证据，输入契约见[通用检查](../../validation/references/general_checks.zh-CN.md)。

## Gaussian 能量解释

`SCF Done` 先保存在 `reference_scf_energy_hartree`。只有输出 route 的明确方法与 SCF 标签匹配，且无已识别的激发态、相关方法、复合能量或自定义 IOp 证据时，才填入 `electronic_energy_hartree`。`energy_evidence` 保存来源、状态和原因；这只解释能量来源，不证明态身份或收敛。

TD/TDA、CIS、MP2/CCSD(T)、双杂化、ONIOM、Counterpoise 等目标不由当前通用 SCF 解析器认证；缺失方法、标签不符或不可读最终能量也不会回退到此前 SCF 值。识别到这些情况后，runner 保留输入、原始日志和解析材料，但不通过目标能量检查。`--validation none` 不绕过能量类型检查。

未评估目标能量时，日志热化学总量仅保存在 `reported_thermochemical_totals`，不能当作该目标方法的 E+ZPE/H/G。IRC/扫描同样区分参考 SCF 点与目标能量。需要更多方法时，使用适用的专用解析和通用 Job，保留方法及态依据，不替换用户指定方法。旧材料缺少能量类型证据时先复核原始输出，不能据缺字段自动确认或否定其科学结论。
