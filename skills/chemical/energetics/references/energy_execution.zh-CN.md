# 独立能量分析 Job

## 内容

- [执行与证据](#执行与证据)
- [热化学输入](#热化学输入)
- [解析适配与组合规则](#解析适配与组合规则)
- [低频处理](#低频处理)
- [构象集合自由能](#构象集合自由能)
- [计量剖面](#计量剖面)
- [扫描切片与报告](#扫描切片与报告)

## 执行与证据

四个 version 1 执行器使用现有 `structure` Python 环境（NumPy/RDKit），
不新增原生求解器、服务或反应类型专属判据：

| 执行器 | 输入角色 | 输入 schema |
| --- | --- | --- |
| `chemical.thermochemistry` | `input` | `chemical-thermochemistry-input/1` |
| `chemical.ensemble-free-energy` | `input` | `chemical-free-energy-ensemble-input/1` |
| `chemical.energy-profile` | `input` | `chemical-energy-profile-input/1` |
| `chemical.scan-slice` | `input` | `chemical-scan-slice-input/1` |

通过普通 Job 的 prepare/start/wait/collect 执行。均输出 `results/result.json`
与 `results/table.csv`，应注册为分析材料。独立入口为
`scripts/energy.py --output-dir NEW_DIR OP --input FILE`，OP 分别为
`thermochemistry`、`ensemble`、`profile`、`scan-slice`。拒绝已有输出目录。
无效输入使 Job 失败，不发布成功结果。独立热化学不需要虚构 R/P、TS 或 IRC。
当前只接受明确的基态声明；激发态/破缺对称态需要专用态身份依据，暂拒绝。

这是对提供的证据做确定性计算，不重新计算 RRHO，也不认证原始来源。
必须将各来源摘要关联已收集 Artifact，并核对几何、方法和频率确属该来源。
相同摘要或态标签不能证明实际收敛、波函数身份和驻点有效性；这些复用 validation。
合同、数值与模拟 Job 验证不能替代真实 Gaussian/CF22D 科学基准。

## 热化学输入

顶层字段：`schema_version`、`electronic`、`conditions`，可选 `thermal`、
`composite`（布尔，默认 false）、`low_frequency_cutoff_cm1`。
未知字段会被拒绝，包括额外叠加的 ZPE 或溶剂修正。

`electronic` 包含：

- `material`：内嵌 `chemical-material/1`，明确电荷、多重度和基态，1–512 个原子。
- `energy_hartree`：有限的电子能 E，不能输入 E+ZPE、H 或 G 冒充。
- `model`：例如 `{"method":"HF","basis":"STO-3G","solvent":null}`。
  无基组方法的 basis 可为 null。溶剂对象为 `{"name":"water","model":"SMD"}`。
- `source_sha256`：`sha256:` 加来源 Artifact 原始字节的 64 位小写十六进制摘要。

`conditions` 示例：

```json
{"temperature_k":298.15,"phase":"gas","standard_state":{"kind":"pressure_pa","value":101325.0}}
```

溶液相要求电子能来源声明溶剂模型，标准态例如
`{"kind":"concentration_mol_l","value":1.0}`。气相要求 solvent=null。
压力/浓度标准态与相态分别记录；选择 1 M 不代表溶液相或添加溶剂化作用。
这里是标准态，不能代替真实反应浓度。单位固定明确，不自动猜测。
没有 thermal 时只有 E，其它量为 null；缺字段不能补零，明确给定零校正有效。

## 解析适配与组合规则

`thermal` 包含 `material`、`model`、`source_sha256`、`temperature_k`、
`standard_state`、`format`、`data`、`rrho`。来源与目标温度必须相同；
单温度总量不能推导另一温度。更换温度需先用原始 RRHO 计算器重新计算。

`rrho` 声明 `stationary_type`（minimum/transition_state）、`geometry_class`
（atom/linear/nonlinear）、正整数 `symmetry_number`、正数 `frequency_scale`，
以及完整的**未缩放**振动频率 `frequencies_cm1`。data 必须是采用所声明缩放因子和
对称数的原始 RRHO 值，尚未施加低频或额外标准态修正。平移/转动应已投影排除。
程序检查几何类别及 3N−5/3N−6 模式数（单原子为零），拒绝零频率；极小值不能有
负频率，一阶 TS 恰好一个负频率。这是记账核对，不是 Hessian/驻点认证。

| format | data |
| --- | --- |
| `corrections` | 仅允许 E_hartree、ZPE_hartree、H_correction_hartree、G_correction_hartree；缺失/null 保留 |
| `gaussian` | 现有 parse_thermochemistry 字典；要求目标能量受支持，日志温度/压力匹配 |
| `cf22d` | 现有 pyscf-thermo/1；要求 temperature_K 和 pressure_Pa 匹配 |

使用 normalized corrections 时，应在来源 Artifact 保留专用目标能量解析证据，
不能把不支持方法的 Gaussian 参考 SCF 能改名成相关能。Gaussian 适配器拒绝
unsupported 目标，绝不读取 reported_thermochemical_totals 代替目标总量。
CF22D 旧 entropy 字段没有显式单位，本模块不消费该字段。两种适配器都会核对已有
总量 = E + 校正（容差 2e-6 Eh，覆盖打印精度）；不从总量反推缺失校正。

H/G 校正相对于电子 E，**已经包含 ZPE**：
`E+ZPE = E + ZPE`、`H = E + Hcorr`、`G = E + Gcorr`。
不能再向 H/G 添加一次 ZPE。模块不接受单独溶剂增量，电子溶剂效应由电子能来源及
模型表示；本版不实现“气相电子能 + 单独溶剂化自由能”的热力学循环。

不同来源摘要或模型必须显式 `composite:true`。高层级电子能与低层级热校正材料需要
相容的态声明及图保持的正旋转配准，全原子 RMSD ≤0.01 Å（映射限 256 原子、
20000 次赋值尝试、64 个保留候选）。无图材料（如 TS）要求
有序原子 ID、元素、同位素及坐标一致，坐标容差 1e-8 Å；乱序无图材料需先显式重排。
结果保留两个模型。显式组合允许低层级气相 RRHO 与高层级溶剂电子能，不能自动替换来源。

仅 G 接受标准态修正。R 用 J mol−1 K−1 时，气体浓度
`c_gas=p/(1000 RT)`，单位 mol/L；`delta_G=RT ln(c_target/c_source)`。
298.15 K、1 atm → 1 M 为每物种 +1.89432845 kcal/mol。按计量求和会自然得到
缔合/解离的 Δn 修正。E、ZPE、H 不变；标准态转换不是溶剂化自由能。

## 低频处理

可选正数 `low_frequency_cutoff_cm1` 启用**仅对熵的谐振频率下限处理**，
不是 Grimme 自由转子插值或完整 quasi-RRHO。对每个稳定的已缩放频率：

`S(ν)=R[x/(exp(x)−1)−ln(1−exp(−x))]`，`x=hcν/(k_B T)`；
`delta_G=T Σ[S(ν)−S(max(ν,νcut))]`。

只向原 RRHO G 添加一次该增量；ZPE、H 保持原 RRHO 值。TS 的负频率单独记录并排除。
阈值以上的模式不变。输出记录频率缩放、阈值、温度及增量；缺少 G 时拒绝处理。
不能把已校正 G 当原始 RRHO 再输入。该模型是明确近似，阈值敏感性、大振幅或受阻
转子问题仍需单独研究。

## 构象集合自由能

输入有 `members`（1–64）、非空 `coverage`，以及
`degeneracy_convention:"additional_unrepresented_basins"`。
每个成员包含 `id`、`thermochemistry`（上面的输入合同）、正整数 `degeneracy`、
非空 `degeneracy_evidence`。

简并度 g 是该成员代表的等价势阱总数，包含自身；无额外简并时填 1。
g>1 的额外势阱不能已经作为另一个显式成员列出，也不能重复计入 RRHO 已包含的转动
对称数/电子自旋多重度。拒绝重复 ID 和 0.05 Å 内相同构象；映射搜索不完整时不能
确认构象不同。成员须具有相同图/同位素/态、极小值 RRHO、电子与热模型、频率处理、
温度/相态/标准态以及 G。不同产物或不同自旋态不能当作本操作的构象集合。

`Gensemble=Gmin−RT ln Σ[g_i exp(−(G_i−Gmin)/RT)]`。
实现用平移后的对数避免上下溢，输出归一化布居、G 和覆盖声明，不虚构集合 H/E。
结果假设提供的独立势阱可互变并已平衡；有限采样和声明的简并度不能证明全局配分和。

## 计量剖面

`species` 对象将 ID 映射到热化学输入或集合自由能输入。可以复用收集结果的
`request` 字段并保持 Artifact 关联；剖面从这些来源重新计算，不信任可编辑的派生 G。
`states` 列表的成员如 `{"id":"R","stoichiometry":{"A":2,"catalyst":1}}`。
系数为正整数（≤1000），状态 ID 唯一，最多 128 个物种和 256 个状态。
催化剂和旁观物种须在每个相关状态显式列出。

`reference` 为参考状态 ID；`quantity` 为 E/E+ZPE/H/G；`unit` 为
hartree/kJ/mol/kcal/mol。可选 `comparisons` 条目有 from、to、kind
（reaction/activation）。差值为末态减初态；反向能垒需显式添加反向比较。
活化能比较中的 TS 依据由调用者提供；模块输出 validated_elementary_step:false，
不因一项数值比较而认证 TS 或基元步骤。

所有状态须守恒元素、同位素和总电荷；拒绝未使用的物种和缺失能量。
方法与条件必须一致；热量比较还要求热模型/频率处理一致。
原子对称数、几何类别和 minimum/TS 标签可以不同。结果逐物种输出多重度声明，
但总自旋耦合及表面连续性为 not_assessed，尤其不能将分离片段多重度直接相加。
最低局部能垒不能代替网络速率或选择性预测。

## 扫描切片与报告

输入为 scan（已收集的终态 chemical-scan-result/1）及 unit。
只输出 1D/2D 成功点的目标值、实际坐标、物理 E，以及相对最低成功点的能量。
失败/待算点即使带数字也只保留在 excluded。检查行摘要、形状、已记录的偏差与
容差及来源证据存在性；不重新测量几何约束，也不重新执行求解器。
全部失败时表为空、参考值为 null；拒绝运行中或未知状态。

CSV 应与 JSON 一起消费：单独 CSV 不包含全部科学条件、来源与范围。
报告图轴应明确数量、单位、参考和条件。离散剖面按离散状态绘制；扫描标成有限
采样势能切片，失败区域保留空缺；不能称为完整 PES 或自由能面。
这四个操作不包含 TST、分支比或动力学网络求解器。
