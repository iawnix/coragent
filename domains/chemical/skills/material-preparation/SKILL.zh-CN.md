---
name: material-preparation
description: 从名称、SMILES 或坐标准备分子材料和明确反应定义，保留身份、电子态、映射和来源。
---

# 材料准备

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#material-preparation)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.resolve@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.resolve-candidates@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.inspect@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.seed@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.reaction@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.compare@1` → `skills/material-preparation/scripts/reaction/prepare.py`；`chemical.material@1` → `skills/material-preparation/scripts/materials/material.py`；`chemical.map-candidates@1` → `skills/material-preparation/scripts/geometry/analysis.py`；`chemical.conformer-compare@1` → `skills/material-preparation/scripts/geometry/analysis.py`；`chemical.reorder-tensors@1` → `skills/material-preparation/scripts/geometry/analysis.py`；`chemical.local-diagnostics@1` → `skills/material-preparation/scripts/diagnostics/diagnostics_job.py`。

在计算或反应研究开始时使用本 Skill。它把名称、SMILES、给定 XYZ 和反应描述转成后续几何与电子结构 Job 可使用的 material 记录。

## 准备流程

1. 将用户原文或坐标作为来源记录保存。
2. 名称用 `chemical.resolve@1` 按配置的解析器处理；SMILES/XYZ 直接用 `chemical.material@1`。保留片段、电荷、多重度、显式氢顺序、立体化学和来源元数据。
3. 名称解析失败时写出带理由的候选 SMILES，用 `chemical.resolve-candidates@1` 检查价态、电荷、立体化学和分子式，再选择研究分支。
4. 用 `chemical.inspect@1` 检查图和价态。反应研究在生成三维初始结构或开始优化之前，先从分子图建立包含显式氢的持久原子身份。
5. 对每个基元步骤假设，用 `chemical.map-candidates@1 --mode reaction` 辅助选择对应关系，并固定已知原子对。保存完整映射和预期键变化，再用 `chemical.reaction@1` 配合 `--transformation` 核验。具体操作见[几何生成前的映射准备](references/reaction_mapping.zh-CN.md)。产物仍在探索时，先固定反应物原子身份，后续假设沿用这些身份建立对应分支。
6. 缺少三维几何时，将选定的映射 SMILES 交给 `chemical.seed@1`，把其逐行 `atoms` 表与 XYZ 一起保存。构象生成和优化继承这些身份；工具改变行序时应用明确的排列。用 `chemical.compare@1` 比较身份、`chemical.conformer-compare@1` 比较构象、`chemical.reorder-tensors@1` 同步重排相关张量。
7. 用 `chemical.local-diagnostics@1` 获取反应中心距离、接触和局部对齐证据，再将完整 material 与映射交给 `reaction-investigation`。

## 已注册操作

`chemical.resolve@1` 解析名称，`chemical.resolve-candidates@1` 检查候选 SMILES，`chemical.material@1` 生成 material，`chemical.inspect@1` 检查图，`chemical.seed@1` 生成初始 3D，`chemical.reaction@1` 核验给定映射和声明的键变化，`chemical.map-candidates@1` 生成映射候选，`chemical.conformer-compare@1` 比较构象，`chemical.reorder-tensors@1` 调整张量顺序，`chemical.local-diagnostics@1` 输出局部几何证据。

通过 generic executor 准备，使用 `job_start` 提交并收集 JSON/几何 Artifact。schema 见[材料输入](references/material_input.zh-CN.md)、[名称解析](references/name_resolution.zh-CN.md)、[反应映射](references/reaction_mapping.zh-CN.md)和[结构分析](references/structure_analysis.zh-CN.md)。

## Further references

- [local diagnostics.zh CN](references/local_diagnostics.zh-CN.md)
- [script layout.zh CN](references/script_layout.zh-CN.md)
- [structure input.zh CN](references/structure_input.zh-CN.md)
