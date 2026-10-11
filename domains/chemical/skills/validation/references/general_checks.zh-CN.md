# 通用驻点、模式与 IRC 证据检查

[English](general_checks.md)。以下版本 1 的 executor 通过普通 Job 在 `structure` 后端独立
执行，输出 `results/result.json` 并保存输入摘要。不改变 Node 状态，也不将检查通过设为
搜索的前置门槛；不导入 DA 拓扑或其验收 profile。

## 内容

- [操作与结论](#操作与结论)
- [驻点证据](#驻点证据)
- [模式归属](#模式归属)
- [IRC 与端点归属](#irc-与端点归属)
- [Gaussian 转换](#gaussian-转换)
- [独立调用](#独立调用)

## 操作与结论

| 入口 | 输入角色 | 检查内容 |
| --- | --- | --- |
| `chemical.stationary-check` | material、evidence | 极小点/一阶鞍点的优化与完整振动谱 |
| `chemical.mode-check` | material、evidence、coordinates | 驻点证据及虚频对声明内部坐标的响应 |
| `chemical.irc-check` | material、evidence、forward、reverse、reactant、product | 来源鞍点证据、路径完整性及相反端点势阱 |
| `chemical.gaussian-evidence` | material、evidence（原始日志） | 将一个 Gaussian section 转为驻点/IRC 证据，本身不作验证结论 |

`material` 为 `chemical-material/1`；IRC 的 material/evidence 指向来源鞍点。
检查结果 `chemical-evidence-check/1` 分别保存 checks、verdict=pass/fail/inconclusive、
范围和输入文件摘要。通过只对应该项标准：模式通过不建立 IRC 连通性，IRC 通过也不证明
虚频符合目标步骤。解释为所提经典 TS 前，应联合审查这两个维度。
组合报告时核对 sources.material 与 sources.evidence 摘要均相同，不能拼接不同结构或
不同计算的通过结果作为一次 TS 验证。

格式无效时执行失败；证据缺失为未确定；明确反证使对应检查失败。当前经典检查要求明确
无约束、ground 态声明、single_surface。约束未知、激发态/broken_symmetry、无势垒模型
和交叉点不套用本判据（来源超范围时 scientific_verdict=not_assessed）。电荷、多重度与
态声明须和材料相容。这不证明真实基态、SCF 稳定性、自旋纯度或连续波函数身份。

## 驻点证据

`chemical-stationary-evidence/1` 是与后端无关的规范化材料。来源摘要仅做归因，不认证
计算或提取正确；保留主要输出及真实 Job/Artifact 派生关系。其它后端可通过经过核验的
adapter/任务脚本提供此合同，不得把缺失事实填成通过值。现有 CF22D 频率 JSON 不含模式
向量，不能单独作为完整模式检查证据。

| 字段 | 合同 |
| --- | --- |
| `material_sha256` | 给定材料文件原始字节的 SHA256，带 sha256: 前缀 |
| `atom_ids` | 与材料当前顺序完全相同的原子 ID |
| `coordinates`、`coordinate_unit` | N × 3 有限数、angstrom；与材料同一坐标系，逐分量差不超过 1e-5 angstrom，不先拟合 |
| `sources` | 非空 `{kind, sha256}` 列表，可增加提取元数据 |
| `calculation` | method、basis、charge、multiplicity、electronic_state、constraints、surface |
| `termination` | normal/error/unknown |
| `optimization` | converged 为布尔/null；criteria 列表；端点优化可附 start_coordinates |
| `frequencies_cm-1` | 完整有符号振动谱，有限数；缺失时 null |
| `normal_modes` | K × N × 3，同原子/坐标系/频率顺序；缺失时 null |
| `mode_representation` | cartesian；质量加权向量须先显式转换 |

calculation 要求方法/基组已知、整数电荷和正整数多重度才能通过；electronic_state 使用
材料的态描述。constraints=[] 明确声明没有约束，null 表示未知；支持的 surface 为
single_surface。这些是记录的假设，不能用来将未知设置改成默认基态。

每条优化 criterion 包含 name、非负 value、正 threshold、unit。支持 max_gradient /
rms_gradient（hartree/bohr）与 max_displacement / rms_displacement（bohr）。通过需要
converged=true、两项梯度判据齐全且每项给定值都数值满足阈值。只有收敛标记不够；保存
求解器实际阈值，不用人为放宽的数值替换。

`--kind minimum|saddle` 默认 saddle。按几何分类要求 3N−6（非线性）、3N−5（线性）
或 0（单原子）振动自由度。中心化坐标 SVD 的第二/第一奇异值比小于 1e-7 为线性，
1e-7 至 1e-4 为近线性并保留未确定；几何退化也不强制计数。输入应投影掉整体平移/旋转，
不能直接提交 3N 个 Cartesian 原始特征值。

`--negative-threshold` 默认正幅值 20 cm−1，小于其负值才是显著负频。
minimum/saddle 要求 0/1 个显著负频；其余小负频全部保存并阻止通过，不能静默丢弃。
`--near-zero` 默认 10 cm−1，不得高于负频阈值；绝对值小于等于它的平坦模式保持未确定。
鞍点还要求非零虚频 Cartesian 向量可用，但向量可用不等于化学归属正确。

## 模式归属

coordinates 输入使用 `chemical-mode-coordinates/1`，一个声明坐标可以是距离、角度、
带符号二面角或加权组合。引用给定材料的局部 atom ID，不是索引或 map 标签。

```json
{
  "schema_version": "chemical-mode-coordinates/1",
  "coordinates": [
    {"name": "质子转移", "direction": 1,
     "minimum_response": 0.02, "minimum_projection": 0.05,
     "terms": [
       {"atoms": ["donor", "H"], "weight": 1, "scale": 1},
       {"atoms": ["H", "acceptor"], "weight": -1, "scale": 1}
     ]}
  ]
}
```

2/3/4 个 ID 分别表示 angstrom 距离、度角度、度二面角。weight 为有限非零值，scale 为
该项原生单位的正数，均默认 1；通过 scale 可显式组合不同单位。direction 为 ±1，表示
多个坐标之间预期的相对变化方向，不要求固定数量的成键或所有坐标等幅变化。

将唯一显著虚频向量按 Cartesian 欧氏范数归一化，`--step`（默认 0.05、最多 0.5 angstrom）
生成正负局部扰动。输出两份几何、各项坐标值、组合中心差分响应（每 angstrom）及对数值
坐标梯度的投影余弦。二面角差按 360 度周期处理，坐标梯度使用 1e-5 angstrom 差分步长。

每个声明坐标必须满足最小绝对响应/投影（默认 0.02/0.05），且所有响应能在一个共同符号
下满足预期相对方向。整体翻转或缩放模式不改变结论；退化坐标/梯度保持未确定。
阈值与坐标选择属于研究假设，应检查敏感性。扰动几何不是优化极小点，不能代替 IRC。

## IRC 与端点归属

forward/reverse 输入为 `chemical-irc-evidence/1`；输入槽位可交换，但实际 direction
必须包含一条 forward 和一条 reverse。每份记录包含驻点合同相同的绑定、calculation、
sources 和坐标单位字段，以及：

- origin_coordinates：固定原子 ID 顺序的 N × 3 坐标，允许一次纯旋转/平移与鞍点比较
  （`--origin-rmsd` 默认 0.01 angstrom），不做对称重新标号或反射。
- complete、max_points_reached：布尔/null，只有明确完成、未达到上限且正常终止才通过。
- points：至少两个 `{index, coordinates, energy_hartree?}`，index 从 1 连续递增。
  能量可缺失，提供时须为有限数；不将参考 SCF 冒充其它目标方法能量。
- endpoint：尚无势阱证据时为 null，否则包含材料及驻点合同的 minimum_evidence。

已有端点材料可用 endpoint.material_json 保存原文件精确 UTF-8 文本，包括换行，
minimum_evidence 继续绑定原文件摘要。也可用 endpoint.material 对象，此时摘要采用
canonical JSON：键排序、逗号/冒号紧凑分隔、UTF-8、Unicode 不转义、无 NaN、无末尾换行。
两种形式只能选一个。路径公共 material_sha256 始终绑定来源鞍点，不是端点。

端点沿用来源原子 ID、元素和同位素，必须与路径末点同坐标系、逐分量误差不超过 1e-5
angstrom。若另做优化，minimum_evidence.optimization.start_coordinates 必须等于
末点，最终几何仍绑定端点材料。保留真实优化输出及来源；填写起始坐标本身不证明优化
运行过。要求同方法/基组、与来源态相容，且无约束极小点检查通过。

reactant/product 是有明确图、几何和相容态声明的参考材料。归属复用有界构象比较
（`--endpoint-rmsd` 默认 0.2 angstrom，`--max-search 20000`，`--max-candidates 64`）。
必须匹配一个目标并明确排除另一个。歧义、未探索完或意外势阱保留实际材料与未确定结论。
两个方向须分别到达不同目标索引，允许方向互换。这检查选定参考构象，不覆盖同一物种的
所有构象。缺极小点证据时继续路径或优化末点，不伪造目标结构。

## Gaussian 转换

`chemical.gaussian-evidence@1 --kind stationary|irc` 读取原始日志与输出原子/坐标系
顺序的材料。`--section-index` 可显式选择零基 section，否则沿用既有最终 section 选择。
复用频率/模式/IRC parser，记录原日志摘要和 section，提取电荷/多重度，核对模式原子序数，
保存真实带坐标路径点。

`--constraints none` 是依据实际输入作出的声明，不从正常终止推断。默认 unknown
阻止经典检查通过；发现已识别约束标记会否决无约束声明。转换器使用当前 HF/DFT SCF
解析范围；其它目标方法/态和显式同位素质量保持未评估。局部 ID 和 ground 态来自材料
声明，不是推断出的真实轨迹或态跟踪证据。IRC 提取保留 endpoint=null，不用完成标记
虚构极小点或归属。CF22D 等原始 payload 需适用的规范化转换，不能不经处理当作本合同。

## 独立调用

路径使用研究 work_dir 下的绝对路径；将准备后的 request_file/request_sha256 和
node_id 交给 job_start，再 job_collect。

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-evidence --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/saddle.log --output <work_dir>/prepared/extract.json -- --kind stationary --constraints none
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.stationary-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --output <work_dir>/prepared/stationary.json -- --kind saddle
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.mode-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --input coordinates=<work_dir>/coordinates.json --output <work_dir>/prepared/mode.json
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.irc-check --version 1 --input material=<work_dir>/saddle/material.json --input evidence=<work_dir>/stationary-evidence.json --input forward=<work_dir>/forward.json --input reverse=<work_dir>/reverse.json --input reactant=<work_dir>/reactant/material.json --input product=<work_dir>/product/material.json --output <work_dir>/prepared/irc.json
```
