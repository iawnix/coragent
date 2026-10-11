# 交叉执行合同

`chemical.mecp-gaussian@1` 输入 `chemical-mecp-input/1`，包含 material、
multiplicities（两个不同且电子计数相容的多重度）、settings；设置见
[Gaussian 电子态计算](../../gaussian/references/electronic_states.zh-CN.md)，要求 theory=ground。
可选 max_steps（0–1000，默认 100）、max_evaluations（1–10000，默认 500）、
step_size（默认 0.2 Å²/Eh）、max_displacement_angstrom（默认 0.1，最大 1）、
gap_tolerance_hartree（默认 1e-5）、gradient_tolerance（默认 1e-4 Eh/Å）、
hessian_step_angstrom（默认 null；需要时取 1e-4–0.01）。

本次选用内置 NumPy 投影平均能量梯度下降，加一阶 Newton 能隙修正。
令 d=∇EA−∇EB、g=(∇EA+∇EB)/2、λ=(g·d)/(d·d)，则
切向梯度为 g−λd，位移为 −α(g−λd)−(EA−EB)d/(d·d)，再按最大逐原子位移截断。
梯度差奇异时拒绝按规则交叉缝处理。两个表面使用相同泛函、基组、气相模型、原子顺序与
几何，每次梯度来自独立有时限的 Gaussian 过程。Hessian 求值同样消耗总预算。

保留已求值迭代、来源摘要、最后完整求值的候选对、检查结果及失败；不自动重提或续跑
未知 Job。达到迭代上限、表面计算失败或 Hessian 预算用尽时 Job 失败并保留部分 JSON。
递归收集原始计算输出；不回退为普通频率/IRC 检查。

`chemical.crossing-check@1` 输入 chemical-crossing-check-input/1，包括各两个
materials、surfaces，相同可选能隙/梯度阈值及 curvature_tolerance（默认 1e-5 Eh/Å²）。
表面采用电子态适配器的 chemical-electronic-evaluation/1，梯度必须是原坐标轴的
Cartesian dE/dR，单位 Eh/Å。投影前核对自旋、模型、几何（打印精度容差 2e-6 Å）、
原子顺序与单位。

检查器分别报告能隙闭合、投影梯度驻点及曲率。每个表面可提供
final.hessian_hartree_per_angstrom2，并必须同时提供 hessian_provenance。
Lagrangian Hessian=(HA+HB)/2−λ(HA−HB)，在移除平移、转动和规则交叉缝法向后
检查切空间本征值。负曲率不能通过局部极小检查，平坦模式保留未确定；缺 Hessian
最多确立数值驻点。搜索器可用指定步长对 Gaussian 梯度中心差分，获得两个 Hessian
并保留全部样本摘要；不自动评估差分步长敏感性。

status=converged 表示满足请求的能隙/投影梯度阈值，曲率另报。
仅曲率通过时 numerical_mecp_conditions 才为 true，不能只看 Job 成功。
validated_global_mecp 始终为 false。合理 S² 和多重度声明不证明波函数稳定性、
同一电子分支或全局最低交叉。本实现是有限局部搜索，没有准 Newton 信赖域、自动重启、
SOC 或跃迁概率计算。

选型依据：实施时本机有 Gaussian 16 A.03，未发现 QBICS/MECP 安装。因此选用可检查的
内置数值算法和 Gaussian 适配器，不虚构 QBICS CLI。验收为解析交叉势、合成导数/日志
合同与本地 Job 测试，不是实际 Gaussian 物理交叉基准。
