---
name: crest
description: 执行有界 CREST 构象搜索、导入和筛选集合、采样刚性片段复合物，并导出成员供独立精修。
---

# CoRAgent CREST 与构象集合

[English version](SKILL.md)

独立构象或复合物准备不要求反应物/产物配对或反应名称。输入合同、Job 示例、
限制与解释见[集合合同](references/crest_ensemble.zh-CN.md)。

根据已有材料选择独立操作：

- `chemical.crest@1`：针对有坐标、已知电荷/多重度且明确声明 ground 态的材料，
  执行有界 CREST 3.0.2 GFN1/GFN2 搜索。
- `chemical.crest-ensemble@1`：导入运行回执及其精确来源材料，保留成员身份推断、
  能量一致性与部分结果状态。
- `chemical.ensemble-select@1`：有界、对称感知的几何聚类及可比电子能筛选，
  逐成员记录选择理由。
- `chemical.complex-sample@1`：组装独立片段的刚性取向/位置，或扰动用户复合物；
  保留原始坐标和原子来源。

每项通过现有 Job 生命周期准备、提交和收集。CREST 使用 `crest` 后端，
需同时配置原生命令与 Python wrapper 环境；导入、筛选和复合物采样使用
`structure`（RDKit/NumPy）。其它经核实的 CREST 版本/功能仍可走通用 Job，
此封装不代表它们已经适配。

使用成员前检查原始文件和逐成员证据。完整搜索回执不等于搜索穷尽、极小点认证或
身份认证。身份/态未知时保留未决；不同方法/溶剂不作能量混排。保留来源集合、
选择记录、导出的 XYZ/material 和精修清单，再以明确相容的方法、溶剂和态提交
独立单点/优化 Job，不能静默切换设置。采样约束不会自动用于后续优化；
CREST 电子能不是自由能。
