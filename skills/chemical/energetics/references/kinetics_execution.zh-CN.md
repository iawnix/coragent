# 基元 TST、分支与显式动力学网络

三个 version 1 执行器均使用 structure 绑定、input 角色与普通 Job 提交/收集，
输出 JSON/CSV。必须联合读取，CSV 不包含全部依据、假设和数值诊断。
独立 energy.py 的 operation 分别是 tst、branching、network。

chemical.tst@1 输入 chemical-tst-input/1：profile 是 Gibbs
[能量剖面输入](energy_execution.zh-CN.md)，另有 reactant_state、transition_state、
active_reactants（物种→整数系数）、transmission_coefficient，以及非空 evidence
引用（source_sha256、note）。可选 concentrations_mol_l 恰好包含全部活性反应物。
反应物须有极小值/集合热化学；活化态一侧恰好一个 TS 热来源及不变的显式旁观物种。
分子数 m 限 1–3，活性系数必须与反应物状态一致。参与活化复合物的催化剂不能当作
旁观物种消去。

`k_m=κ k_B T/h (c°)^(1−m) exp(−ΔG‡/RT)`，单位分别为 s^-1、
L mol^-1 s^-1、L² mol^-2 s^-1。压力标准态按 p/(1000 RT) 转为 mol/L。
共同标准态变化时，ΔG‡ 和浓度前因子一致变化，不改变物理速率。
实际初始通量 `k_m Π c_i^ν_i`，单位 mol L^-1 s^-1；浓度为零时通量为零。
浮点速率下溢时保留对数速率。κ 必须显式给定且在 (0,1]，不推断隧穿增强、扩散或
自动再穿越模型。拒绝负势垒和仅 E 的输入。引用会保留，但 elementary_step_certified
为 false；需先审查实际模式/IRC 证据，才能将条件速率用于物理结论。

chemical.branching@1 输入 chemical-branching-input/1：channels 将 2–32 个 ID
映射到 TST 输入；assumptions 恰好包含三个 true：equilibrated_common_precursor、
irreversible_products、no_product_interconversion。前体计量、活性物种、来源、
条件及模型须完全一致；填写实际浓度时也须一致且为正，零前体初始分支未定义。
同一活化复合物不能靠不同标签/注释重复计数。稳定对数归一化输出初始分支比例，
不代表随时间产率。不同前体、可逆产物、耗尽、循环和构象互变需网络分析。
产物自由能排序与动力学排序应分别报告。

chemical.kinetic-network@1 输入 chemical-kinetic-network-input/1：

- species：1–64 个 ID 到明确基态 chemical-material/1 的映射。
- reactions：1–128 条反应，每条有唯一 id、reactants、products、forward、可选
  reverse；两侧以正整数计量，总级数 ≤8。催化剂显式出现在两侧及速率方程中。
- 速率可用 TST 输入，或 `{value,order,unit,source_sha256,note}`。m 级的 unit
  字面值为 `(mol/L)^{1-m}/s`，如一级 `(mol/L)^0/s`、二级 `(mol/L)^-1/s`。
  TST 来源还需与网络物种材料、活性计量、温度绑定，集合来源使用明确绑定的代表材料。
- temperature_k 为正数；initial_mol_l 包含全部物种，包括零值；times_s 有
  2–1001 个从零开始严格递增的时间。
- 可选 solver：rtol（默认 1e-7）、atol_mol_l（1e-12）、max_steps（100000，
  最大 1000000）；拒绝大于 1e-2/1e-3 的宽松容差。

模型是封闭、恒容、充分混合的质量作用动力学：`dc/dt=S v`，
`v_j=k_j Π c_i^νij`；逆反应展开为独立通道。逐反应核对原子、同位素、电荷守恒，
监测全部计量矩阵左零空间不变量，包括隐藏守恒片段与催化剂。
自适应双步长 RK4 使用 Richardson 修正及显式局部误差估计；出现负值的中间阶段/结果
会缩小步长重试，不截断为零。保留观察点、末态、步数、拒绝次数、误差及守恒漂移。

此显式算法不是通用刚性求解器。预算耗尽、步长下溢或守恒失败时 Job 失败并保留
部分结果，绘图/报告前须检查 status。用户给定的正逆速率不自动保证热力学详细平衡，
报告为 not_assessed。不提供恒浓度外源、传质、随机化学或自动机理发现。
条件/模型敏感性应通过明确独立 Job 比较，保留输入摘要及覆盖范围。
