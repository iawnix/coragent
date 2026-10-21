# 调用卡片

这些卡片说明工具选择和结果解释。将路径替换为 `research_create` 或 `research_read` 返回的绝对
`work_dir`，提交请求时绑定输入 Artifact。

## 分析已映射的反应位点

当已有 `chemical-material/1` 和显式原子映射键变化时使用：

```text
chemical.reactive-sites@1
input=input.json
```

输入形状如下：

```json
{
  "schema_version": "chemical-reactive-sites/1",
  "material": {"schema_version": "chemical-material/1"},
  "bond_changes": [
    {"atoms": ["C", "F"], "before": 0, "after": 1},
    {"atoms": ["C", "Cl"], "before": 1, "after": 0}
  ],
  "reaction_family": "sn2"
}
```

把返回的 `sites[*].hypotheses` 作为取向生成的显式备选。`opposite_face` 是探索用备选，不表示
反应一定具有立体化学歧义。

## 生成反应取向

对选定的位点使用 `chemical.reactive-pose@1`。把显式原子对和距离提示复制到 `bond_changes` 和
`sampling`，保留返回的变换和拒绝诊断。如果对多个构象重复搜索，在来源信息中记录构象 ID。

## 约束预优化

使用 `chemical.scan-xtb@1`，设置一个扫描轴和一个目标值，在保留反应坐标的同时放松取向。扫描轴
使用局部原子 ID：

```json
{
  "schema_version": "chemical-scan-input/1",
  "material": {"schema_version": "chemical-material/1"},
  "settings": {
    "method": "gfn2", "threads": 2, "timeout_seconds": 600,
    "solvent_model": "gas", "solvent": null, "opt_level": "tight",
    "force_constant": 1.0
  },
  "axes": [{
    "kind": "distance", "atoms": ["C", "F"],
    "values": [2.2], "unit": "angstrom", "tolerance": 0.08
  }]
}
```

检查 `points[*].actual`、`deviations`、`status`、`energy_hartree` 和 `evidence`。点失败或塌缩时，
调整取向、构象或约束假设；不要把它当作反应不可能的证据。交给 QST 或 NEB 时保留受限几何的
候选来源。

## 继续路径搜索

已有产物映射和 guess 对应关系时使用 QST；主要不确定性集中在一两个坐标时使用受限扫描；只有
端点相容且初始图像保留预期反应中心变化时才使用 NEB/GSM。具体合同查候选生成 Skill 的路径参考。

## 通用 Job 调用

用通用 executor CLI 准备声明的执行器，再将 `request_file`、`request_sha256` 和 `node_id` 提交
给 `job_start`。不要用控制面 Python 直接调用科学脚本。收集终态结果并检查后，再选择下一条假设。
