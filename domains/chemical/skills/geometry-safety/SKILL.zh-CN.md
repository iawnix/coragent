---
name: geometry-safety
description: 检查分子和反应候选坐标是否存在致命输入错误，同时允许反应中心处于成键、断键和非平衡几何。
---

# 几何安全检查

当坐标即将进入 Gaussian、xTB、QST、NEB 或其它电子结构计算时使用，或需要客观筛查失败路径
image 时使用。

这是输入安全检查，不是过渡态验证。必须拒绝非有限坐标、原子身份/顺序错误、原子核塌陷和
非反应区域的严重短接触；必须允许声明反应中心中的成键、断键、角度和配位处于非平衡状态。
不能用正常极小值的键长或角度筛掉 TS 初猜。

使用 `skills/_shared/geometry_safety.py` 中的确定性检查器。原始 Gaussian 输入要检查每个显式
笛卡尔坐标块。`Geom=AllCheck` 的坐标在文本中不存在，该部分必须报告为 `not_assessed`，不能
声称通过。

结果有两个独立含义：

- `verdict=unsafe`：不要启动计算，保留硬失败原因；
- `verdict=safe`：只表示坐标没有明显崩坏，不代表极小点、鞍点或机理结论。

声明的反应原子对可以免除非键短接触阈值，但永远不能免除绝对塌陷阈值。已知反应上下文时提供
从零开始的反应原子对索引。按输入选择 `general`、`reaction_seed`、`ts_candidate` 或 `path_image`
profile。

本 Skill 不规定研究顺序。Agent 仍可根据证据选择 QST、NEB、扫描、直接 TS 优化或诊断；它只
阻止明显损坏的坐标进入求解器，并记录反应中心非平衡几何的警告。

需要输入格式和 CLI 合同时阅读[geometry_safety.zh-CN.md](references/geometry_safety.zh-CN.md)。
