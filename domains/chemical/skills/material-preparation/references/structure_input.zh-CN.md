# 结构准备

用 `chemical.inspect@1` 检查 SMILES 的分子图、分子式、电荷和未指定立体化学。
根据研究目标选择立体异构体，或用 `--enumerate-stereo` 枚举候选。

反应研究先按[映射流程](reaction_mapping.zh-CN.md)准备原子身份和对应关系。
`chemical.reaction@1` 接受映射的 `reactants>>products`，检查元素/电荷守恒及原子对应，
输出键变化。通过 `--transformation <file.json>` 提供 `kind: "explicit"`、
`bond_changes` 和可选 `hydrogen_changes`，将当前假设与分子图核对。
结果使用 `chemical-reaction/2`。

用 `chemical.seed@1` 的 `--smiles`、`--charge`、`--multiplicity` 和空的 `--output-dir`
生成采用固定 ETKDG 随机种子的显式氢 XYZ。电荷、多重度按分子图和电子数确定。
每个 seed 保存 SHA256、异构体来源及原子表，供后续计算沿用。

## 结构对照

inspect 和 seed 包含 `chemical-identity/1` 对象，保存规范异构 SMILES、电荷、RDKit
版本及内容身份。将选用目标登记为 Artifact，通过 Node 的 `subjects.target` 引用。
准备 `chemical.compare@1`，指定 `--input target=<inspect.json>` 与
`--input actual=<结构JSON或几何XYZ>`。XYZ 需追加
`-- --actual-format xyz --charge <实际电荷>`；默认读取结构 JSON。
收集 `results/comparison.json`，其中记录 match、mismatch 或 indeterminate、
对照结构及检查范围。XYZ 的键级由几何推断。用 `check_refs` 引用检查材料，
用 `subjects` 区分目标和计算结构；利用差异指导研究，检查不限制记录结论或继续工作。

## 生成初始结构时保留原子身份

反应研究先完成[映射准备](reaction_mapping.zh-CN.md)，再嵌入三维坐标。
`chemical.seed@1` 保留输入的显式氢 map 标签，记录原文 `source_smiles`。
每个 seed 包含 `atom_index_base: 0` 及按 XYZ 行序排列的 `atoms` 表，其中记录
`xyz_index`、`element`、`atom_map`、`isotope`、`origin` 和 `parent_atom_index`
（单键连接的 H 的母原子行号）。表、XYZ 和 SHA256 一起保存。行号对应这一份 seed，
与规范 SMILES 的遍历顺序分开记录。

准备反应时采用包含全部显式氢标签的映射 SMILES。输入使用隐式氢时，seed 会补齐坐标，
以 `origin: "added_hydrogen"`、`atom_map: null` 记录这些 H 及其母原子行号。
先在图上分配共用的反应标签，再分别生成片段，使它们沿用同一编号空间。
后续构象和优化结果继承原子表；行序改变时记录明确的排列。
