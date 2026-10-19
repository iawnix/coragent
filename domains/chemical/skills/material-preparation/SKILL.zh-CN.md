---
name: material-preparation
description: 从名称、SMILES 或坐标准备分子材料和明确反应定义，保留身份、电子态、映射和来源。
---

# 材料准备

[English version](SKILL.md)

在计算或反应研究开始时使用本 Skill。它把名称、SMILES、给定 XYZ 和反应描述转成后续几何与电子结构 Job 可使用的 material 记录。

## 准备流程

1. 将用户原文或坐标作为来源记录保存。
2. 名称用 `chemical.resolve@1` 按配置的解析器处理；SMILES/XYZ 直接用 `chemical.material@1`。保留片段、电荷、多重度、显式氢顺序、立体化学和来源元数据。
3. 名称解析失败时写出带理由的候选 SMILES，用 `chemical.resolve-candidates@1` 检查价态、电荷、立体化学和分子式，再选择研究分支。
4. 图和价态检查用 `chemical.inspect@1`；缺少 3D 几何时用 `chemical.seed@1`。已有坐标应保留并检查，不要无理由替换成新嵌入。
5. 反应使用 `chemical.reaction@1`，提供反应物/产物映射和 `--transformation`；多个对应关系时用 `chemical.map-candidates@1`。
6. 用 `chemical.compare@1` 比较计算结构与目标；用 `chemical.conformer-compare@1` 做考虑对称性的几何比较，用 `chemical.reorder-tensors@1` 处理梯度、Hessian 和模式的原子顺序。
7. 用 `chemical.local-diagnostics@1` 获取反应中心距离、接触和局部对齐证据，再将完整 material 与映射交给 `reaction-investigation`。

## 已注册操作

`chemical.resolve@1` 解析名称，`chemical.resolve-candidates@1` 检查候选 SMILES，`chemical.material@1` 生成 material，`chemical.inspect@1` 检查图，`chemical.seed@1` 生成初始 3D，`chemical.reaction@1` 建立反应定义，`chemical.map-candidates@1` 生成映射候选，`chemical.conformer-compare@1` 比较构象，`chemical.reorder-tensors@1` 调整张量顺序，`chemical.local-diagnostics@1` 输出局部几何证据。

通过 generic executor 准备，使用 `job_start` 提交并收集 JSON/几何 Artifact。schema 见[材料输入](references/material_input.zh-CN.md)、[名称解析](references/name_resolution.zh-CN.md)、[反应映射](references/reaction_mapping.zh-CN.md)和[结构分析](references/structure_analysis.zh-CN.md)。

## Further references

- [local diagnostics.zh CN](references/local_diagnostics.zh-CN.md)
- [script layout.zh CN](references/script_layout.zh-CN.md)
- [structure input.zh CN](references/structure_input.zh-CN.md)
