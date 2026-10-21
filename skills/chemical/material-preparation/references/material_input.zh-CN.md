# 保留原始输入的结构材料

[English](material_input.md)。`chemical.material@1` 将 SMILES、名称或单帧 XYZ 导入为
`chemical-material/1` 材料。它只做结构与字段一致性检查，不联网、不生成几何、不优化、
不推断 XYZ 键级，也不验证电子态。可独立调用，不要求产物、反应映射或 TS。

## 输入

准备 `chemical-material-input/1` JSON，必填 `schema_version`、`format` 和非空 `text`。
`format` 为 `smiles`、`name` 或 `xyz`。`text` 保存用户原文，不先转换为另一种结构格式。
文件最多 4 MiB；字段拼写错误和未支持字段会拒绝，避免静默忽略研究信息。

```json
{
  "schema_version": "chemical-material-input/1",
  "format": "xyz",
  "text": "6\n用户给定复合物\nO 0 0 0\nH 0 0 0.96\nH 0 0.93 -0.24\nO 5 2 1\nH 5 2 1.96\nH 5 2.93 0.76\n",
  "arrangement": "complex",
  "fragments": [[0, 1, 2], [3, 4, 5]]
}
```

示例未指定电荷、多重度与电子态，输出保留未知；不会补成中性单重态。

| 可选字段 | 语义 |
| --- | --- |
| `charge` | 整数或 null；有分子图时从图取得电荷，显式值须一致。XYZ 本身不提供电荷 |
| `multiplicity` | 正整数或 null；不默认单重态。已知原子与电荷时检查电子数奇偶兼容性 |
| `electronic_state` | 对象，`kind` 为 unspecified/ground/excited/broken_symmetry，可附 label、method、note；excited 的 root 必须为正整数且指定 method。描述属于声明，不是波函数证据 |
| `arrangement` | unspecified/isolated_species/separate_reactants/complex，默认 unspecified。断开的分子图不自动判成复合物或游离反应物 |
| `fragments` | 用输入原子零基索引列出所有片段，必须恰好覆盖全部原子。有图时与图连通分量核对；XYZ 无图时只记录用户分组 |
| `atom_ids` | 为每个输入原子提供唯一局部标识；默认 atom_1、atom_2 等，不意味着不同材料同名原子互相对应 |
| `new_to_old` | 输出第 i 个原子取输入哪一行，零基、完整置换；不提供则保持原顺序 |
| `graph` | name/xyz 可选的已选择图，包含 smiles、source（user/lookup/agent）和必填 note 说明来源。name 选择沿用既有 resolve/resolve-candidates 结果；导入器不认证名称与图的对应 |
| `graph_to_input` | XYZ 同时提供 graph 时必填：每个扩氢后图原子对应哪个输入 XYZ 行，零基完整置换。检查元素与数量，不证明几何/立体化学身份 |
| `coordinate_unit` | 当前只接受 XYZ 的 angstrom；未提供时按标准 XYZ 约定并记录来源。其它单位先做显式转换，保留原始材料 |

SMILES 保留显式 H、同位素和 atom-map 标签，扩展隐式 H 后建立原子表，不嵌入坐标。
当前接收单个普通分子 SMILES；额外名称、多条记录、CXSMILES 扩展及通配原子需先明确处理，不能静默丢弃。
顺序为 RDKit 解析的显式原子，随后是自动补充的 H；输出记录 RDKit 版本以及每个原子的来源。
`atom_ids`、`fragments` 和 `new_to_old` 均针对这个完整顺序。部分 map 标签可保留，重复标签拒绝；
材料局部编号不等于完整反应原子映射。

XYZ 只接受单帧、元素符号和三坐标，所有数值必须有限。多帧、额外原子列、同位素专用符号
或非 angstrom 单位需先明确处理，不能静默丢弃。已给坐标不经过嵌入、对齐或优化。
可在 graph 中保留同位素归属，但后续 XYZ 求解器输入仍须另行支持同位素质量。

只有名称且未选择 graph 时，材料仍可登记和引用，`unknown_fields` 明确列出缺失结构等信息。
继续名称解析或有来源的候选推断即可，不必伪造产物/映射；选择后生成新的材料并引用之前的来源。

## 执行与输出

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.material --version 1 --input material=<work_dir>/material-input.json --output <work_dir>/material-request.json
```

提交返回的 request_file/request_sha256 与 node_id 到 `job_start`，结束后用 `job_collect` 收集。
输入 JSON 自身被 Job 固定摘要；来源证据可通过既有 input-artifact 和 Result 引用关联。
`graph.source/note` 是输入归因，不取代这些执行来源与证据引用。

| 产物 | 内容 |
| --- | --- |
| `results/material.json` | 原始输入与摘要、可选图身份、原子、片段、态声明、未知字段和检查范围 |
| `results/source.txt` | `text` 原文的 UTF-8 字节，保留数值精度、换行与注释 |
| `results/atom_order.json` | chemical-material-order/1，input/output atom IDs、new_to_old 与逆置换 old_to_new，index_base=0 |
| `results/geometry.xyz` | 仅 XYZ 输入产生；默认与 source.txt 完全相同；指定置换时只重排行，保持坐标值和相对取向 |

`geometry.status=supplied_not_assessed` 不否定用户已有优化，也不认证其收敛。电荷/多重度奇偶
兼容不证明真实电子态；excited/root 的记录不扩展计算后端能力。分子图 identity 可供现有
`chemical.compare` 比较，不能据此认定构象、态或名称正确。

后续单点或优化直接使用收集的 geometry.xyz，并明确选择电荷、多重度和适用方法。
缺少必要计算设置时依研究依据补充或分支；登记材料本身不强迫先解决所有未知字段。

本入口只变换原子行顺序，不处理梯度、Hessian 或振动向量，也不自动寻找反应映射。
已有计算张量不能仅靠重排 XYZ 继续复用；这些操作使用独立的
[映射候选、构象比较与张量重排入口](structure_analysis.zh-CN.md)，保留搜索覆盖与张量表示边界。
