---
name: structure-assessment
description: 将分子或反应候选几何整理成有证据边界的结构描述，供下一项计算使用。
---

# 结构评估

[English version](SKILL.md)

在选择或修正计算前使用本 Skill，建立 material 的共同描述：身份、分子图、片段、电子态声明、反应中心几何和与参考结构的比较。

## 检查内容

提供 material JSON 和 context JSON；context 可包含 `role_hint`、`reaction_center`、`bond_changes` 及同原子顺序的参考结构。执行器报告原子顺序、图是否可用、片段、电荷/多重度、局部距离、压缩/伸长、片段分离和几何观察，也列出未解决输入与后续操作。

根据报告决定生成种子、采样构象、改变反应姿态、准备路径或进入电子计算。把真实反应中心距离和片段接触与键变化对照；非平衡距离可以是有意的 TS 种子。

## 已注册执行器

`chemical.structure-cognition@1` 位于 `skills/structure-assessment/scripts/run.py`，参数为 `--material`、`--context`、`--output`。通过 Job 执行，并把报告附到 material 或 candidate Artifact。坐标筛选配合 `geometry-preflight`，图和映射修复配合 `material-preparation`。

context schema 和输出字段见[结构评估](references/structure_assessment.zh-CN.md)。报告是观察记录；机理、TS 和能量学决定由对应 Skill 基于它完成。
