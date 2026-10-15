# 映射 QST2 输入准备

`scripts/prepare_path.py` 根据声明的基元步骤准备 Gaussian 输入，不推断产物、不选择机理、
不执行 Gaussian，也不认证鞍点。显式变换使用 `chemical.path-candidates@1`，不需要按反应名称
新增工具。IRC 输入准备由 `validation` 独立实现；候选生成不提供也不导入 IRC 实现。

## 内容

- [输入说明](#输入说明)
- [几何策略](#几何策略)
- [执行与来源记录](#执行与来源记录)

## 输入说明

登记 `chemical-path-spec/1` JSON Artifact，提供映射反应物/产物、完整的预期键变化和
显式 Gaussian 设置。以下开环假设使用通用的单片段策略：

```json
{
  "schema_version": "chemical-path-spec/1",
  "mapped_smiles": "[CH2:1]1[CH:2]=[CH:3][CH2:4]1>>[CH2:1]=[CH:2][CH:3]=[CH2:4]",
  "transformation": {
    "kind": "explicit",
    "bond_changes": [
      {"atoms": [1, 2], "before": 1, "after": 2},
      {"atoms": [1, 4], "before": 1, "after": 0},
      {"atoms": [2, 3], "before": 2, "after": 1},
      {"atoms": [3, 4], "before": 1, "after": 2}
    ]
  },
  "candidate_strategy": "mapped_endpoints",
  "method": "M062X", "basis": "6-31G**", "charge": 0,
  "multiplicity": 1, "threads": 2, "memory_mb": 1000
}
```

两端 atom-map ID 必须唯一且对应，键级 0 表示无键。可选 `hydrogen_changes` 使用
`{atom, before, after}` 计数。迁移的 H 必须在 SMILES 中显式映射，仅氢计数不足以保留
原子轨迹。准备器核验原子对应、元素/同位素及电荷守恒、声明变化、总电荷和电子数/多重度
奇偶兼容性。整个流程使用同一个指定电荷/自旋面，不处理跨自旋路径。当前 Gaussian
写入器只输出元素符号，拒绝同位素特定质量；这类任务应使用显式求解器输入。

## 几何策略

| candidate_strategy | 输入与行为 |
| --- | --- |
| `mapped_endpoints` | 显式 spec 未提供 endpoints 时的默认策略。两侧各需一个连通片段，通过确定性 RDKit 嵌入、可选 UFF 松弛和刚体对齐生成 QST2 种子，不附加特定反应几何规则。 |
| `provided_endpoints` | 提供 endpoints 时的默认策略。保留输入坐标，包括多片段取向。要求 `--conformers 1` 且不使用 `--enumerate-stereo`；每组明确几何单独提交。 |
| `diels_alder` | 旧 DA spec 的兼容策略，见其[范围和验证器](gaussian_path.zh-CN.md)。其他反应不受该策略的契约限制。 |

提供几何时，`endpoints` 恰好包含 `reactants` 和 `product`。每端逐原子提供记录，包括 H；
输入行顺序可以不同。单行形如 `{"atom":[0,1,0],"element":"C","xyz":[0.0,0.0,0.0]}`：

- 显式映射原子（含显式 H）用 `atom: [0, map_id, 0]`。
- 自动补充的 H 用 `atom: [1, parent_map_id, ordinal]`，ordinal 在每个母原子下从 1 开始。
  提供几何时优先对所有 H 做显式映射。
- `element` 必须与映射图对应，`xyz` 是三个有限数字，单位 Å。

两端必须具有相同原子键。未知、重复、缺失的键、错误元素和原子重合会在写输出前拒绝。
提供的坐标不会被优化，也未自动验证其图/立体化学身份，这些必须另行检查。通用嵌入策略
不推断多片段相对取向，应显式提供。这是端点种子准备器，不是通用约束优化器；扫描等
约束任务使用显式求解器输入。

自动构造支持 `--conformers 1..8`，反应物立体化学需明确。`--enumerate-stereo` 可枚举
未指定的产物立体化学，上限 16；输出会报告上限，不能据此认定覆盖完备。错误输入在创建
输出前拒绝，各分支的嵌入失败则保留在 `candidates.json` 中供复核。

## 执行与来源记录

使用 Node 返回的 work_dir，未关联时使用工作区 research/work/。以下占位符替换为
实际绝对路径和返回的 Artifact 引用：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.path-candidates --version 1 --input spec=<work_dir>/spec.json --input-artifact <spec-ref> --output <work_dir>/candidates-request.json -- --conformers 1
```

将返回的 request_file/request_sha256 和 node_id 交给 job_start，Job 终止后收集。
成功分支包含带摘要的 spec.json、atom_order.json、reactants.xyz、product.xyz 和 ts.gjf。
分支 spec 通过 CoRAgentSpec 绑定输入标题，保留其收集后的 Artifact 身份。Job 会暂存并
固定所有 helper 模块的摘要。生成几何不等于验证过渡态。
独立片段组装或已有复合物扰动使用 `chemical.complex-sample@1`；CREST 和集合筛选
见[集合合同](../../crest/references/crest_ensemble.zh-CN.md)。导出种子需显式对应到本文
端点原子键，并另行精修；复合物采样本身不确定基元步骤或过渡态。
