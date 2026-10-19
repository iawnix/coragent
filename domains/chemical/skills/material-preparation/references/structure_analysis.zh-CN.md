# 映射候选、构象比较与张量重排序

[English](structure_analysis.md)。三个独立 Job 使用 `structure` 后端（RDKit、NumPy），
统一输出 `results/result.json`。比较两个构象、重排张量无需构造 TS 任务或产物。
输入及选用候选分别作为证据保留，不覆盖已有材料。

## 内容

- [映射候选](#映射候选)
- [构象比较](#构象比较)
- [张量重排序](#张量重排序)
- [独立调用](#独立调用)

## 映射候选

`chemical.map-candidates@1` 的 `left` / `right` 输入为
[材料导入](material_input.zh-CN.md)产出的 `chemical-material/1`。两者均需显式分子图，
有 XYZ 时还需图与坐标行的对应；不推断 XYZ 键级。未解析名称或缺图返回 `not_assessed`。

默认 `--mode reaction` 搜索保持元素/同位素、总电荷相等的双射，包含显式 H。
按键级变化绝对值之和保留搜索中找到的最优候选。这是图编辑启发式，不是机理推断、
概率、TS 搜索或原子真实运动轨迹证明。缺原子、缺反离子、声明电荷不同会产生
`incompatible`，不能解释成该化学反应不可能发生。

`--mode identity` 另外要求分子图及已指定立体化学相同，保持局部电荷、自由基数和键级。
共享的显式 atom-map 标签固定对应，不同非零标签不能匹配。局部 atom ID 不是 map。
可用 `--fixed-pairs '[["左侧ID","右侧ID"]]'` 增加一一对应约束；与 map 冲突时拒绝。

边界为最多 256 原子，`--max-search` 为 1..1000000（默认尝试 20000 次赋值），
`--max-candidates` 为 1..256（默认保留 64 个同分最优候选）。大体系或高度对称体系
可能达到上限。必须结合 `search_complete` 与 `candidate_limit_reached` 解读；只保存
一个候选不等于唯一。`ambiguity` 为 multiple/unique/unknown/none，
`best_count_observed` 记录实际发现的当前最优叶子数量。搜索耗尽预算且未找到候选为
`inconclusive`，不能当作不相容。

结果 `chemical-correspondence/1` 中，每个候选有 `left_to_right`（两边**当前顺序**的
零基索引）、局部 ID `pairs`、键变化和 `right_order`。后者是
`chemical-material-order/1`，将右侧原子排成左侧对应顺序，但保留右侧自己的 ID；
不改名、不认证候选的物理真实性。两份源文件均以 SHA256 绑定。

## 构象比较

`chemical.conformer-compare@1` 使用同样输入和映射预算，生成 identity 对应并比较给定的
angstrom 坐标。不嵌入、不优化、不分别移动片段。对每个保留映射进行全原子、无质量
加权 Kabsch 拟合：整个结构仅允许一次平移和行列式 +1 的旋转，禁止反射拟合。
已指定立体化学不同的图在拟合前就标为不相容。

`--rmsd-threshold` 默认 0.1 angstrom。可用
`--internal-coordinates '[["a","b"],["a","b","c"],["a","b","c","d"]]'`
指定距离、角度和带符号二面角，均引用**左侧局部 atom ID**。
`--distance-tolerance` 默认 0.1 angstrom；`--angle-tolerance` 默认 10 度，
二面角差按 360 度周期处理。退化角度/二面角保持未评估。同一个映射必须同时满足 RMSD
与所有指定内部坐标。阈值由研究目标选择，不是通用构象分类标准。

`chemical-conformer-comparison/1` 将 `geometry_status` 与 `state_comparison` 分开。
覆盖不完整时，找到满足条件的映射仍可作为几何匹配证据；否定几何匹配则需要搜索完成、
候选完整保留且全部未通过，否则为 `inconclusive`。`best` 是已评估中最低 RMSD 候选；
`matching_candidate` 是同时满足所有条件者中最低 RMSD 候选（若存在）。两者的
`candidate_index` 指向 `correspondence.candidates`。变换采用行向量：
`aligned_right = right[mapping] @ rotation + translation`。

已知电荷、多重度或态声明冲突时，即使几何匹配，总体 `status` 也为 `state_conflict`。
未知设置保留未知；相同方法/root/label 不证明波函数身份相同。
`status=geometry_match` 仅表示几何证据。不自动合并材料，也不据此证明优化收敛、
能量等价或电子态跟踪成功。

## 张量重排序

`chemical.reorder-tensors@1` 接收 `tensors`（`chemical-tensors/1`）和 `order`
（`chemical-material-order/1`）。原始输入顺序的张量可使用导入器 atom_order.json；
右侧材料当前顺序的张量可使用选定映射候选中单独提取的 `right_order`。不能重复应用置换。
`atom_ids` 必须与 `order.input_atom_ids` 完全一致，不能通过重命名绕过不一致。

```json
{
  "schema_version": "chemical-tensors/1",
  "atom_ids": ["atom_1", "atom_2"],
  "axis_order": "atom-major-xyz",
  "representation": "cartesian",
  "units": {"gradient": "hartree/bohr"},
  "gradient": [[0.1, 0, 0], [-0.1, 0, 0]]
}
```

至少提供一个张量；仅支持非质量加权 Cartesian 表示。每个已提供张量必须有明确非空单位
标签，原样保留，不转换或认证单位。可选数组如下：

| 字段 | 形状 / 含义 |
| --- | --- |
| `coordinates`、`gradient` | N × 3，置换原子行 |
| `hessian` | 对称 3N × 3N，按 atom-major xyz 索引同时置换两轴 |
| `modes` | K × N × 3 Cartesian 位移，置换原子轴，模式顺序不变 |
| `masses` | N 个正值，单位 atomic mass unit，置换原子轴 |
| `elements` | N 个元素符号，置换原子轴 |
| `frequencies_cm-1` | K 个有限有符号波数，须有对应 modes，模式顺序不变 |

拒绝非有限数、布尔值、错误形状/ID/逆置换、非对称 Hessian、质量加权表示和未知字段。
输出仍为 `chemical-tensors/1`，保留单位、置换/逆置换、来源摘要及此前 provenance，
可再次输入完成逆置换。不做空间旋转、质量变换或模式归一化。构象拟合与原子重排是
不同操作：只重排 XYZ 不能授权复用旧张量，构象拟合所得旋转也不会自动应用到张量。

## 独立调用

使用研究 work_dir 内的绝对路径。准备请求后，将 request_file/request_sha256 和
node_id 交给 `job_start`，再 `job_collect` 收集材料。

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.map-candidates --version 1 --input left=<work_dir>/reactant/material.json --input right=<work_dir>/product/material.json --output <work_dir>/prepared/map.json -- --mode reaction --max-candidates 64
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.conformer-compare --version 1 --input left=<work_dir>/first/material.json --input right=<work_dir>/second/material.json --output <work_dir>/prepared/conformers.json -- --rmsd-threshold 0.1
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.reorder-tensors --version 1 --input tensors=<work_dir>/tensors.json --input order=<work_dir>/selected-order.json --output <work_dir>/prepared/reorder.json
```
