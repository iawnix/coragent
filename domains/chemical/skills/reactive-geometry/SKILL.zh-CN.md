---
name: reactive-geometry
description: 使用反应中心局部坐标、显式编辑和有来源的模式位移构建反应复合物并修正 TS 猜测。
---

# 反应几何构建

[English version](SKILL.md)

分离反应物需要化学上合理的接近几何，或失败的扫描、NEB、优化、IRC 帧需要定向修正时使用本 Skill。它编辑坐标并保留来源，再把候选交给候选生成或受限精修。

## 构建反应姿态

从显式原子 ID 和 `bond_changes` 开始。`chemical.reactive-sites@1` 根据映射结构生成反应中心角色、局部坐标、可选进攻面和接近假设；再把每个合理假设交给 `chemical.reactive-pose@1`，采样片段距离、进攻锥、扭转角和无碰撞刚性放置。

若存在多个亲核位点、亲电面、催化剂取向、质子接力或构象，应保留多个姿态。根据局部取代基方向和空间可达性选择进攻轴；按预期键级和扫描范围设置距离。姿态生成期间保持片段内部几何。

## 精修和修正

用 `chemical.scan-xtb@1` 或 `chemical.scan-gaussian@1` 围绕成键/断键距离、角度或二面角做受限预优化。一点或短程松弛扫描可消除碰撞并保留反应中心应变；结果帧交给 `candidate-generation`，不直接当作 TS。

恢复失败搜索时，根据梯度、虚频模式、路径和反应中心证据选择来源帧。`chemical.reactive-geometry@1` 支持定向刚性放置、群组距离/角/二面角编辑和 Cartesian 模式位移。应用模式或梯度前绑定精确 material digest、原子顺序和坐标轴。若第一次搜索坍缩，改变方向、群组、构象或机理后重用操作。

## 已注册操作与交接

`chemical.reactive-sites@1` 做局部位点/坐标分析，`chemical.reactive-pose@1` 生成片段姿态集合，`chemical.reactive-geometry@1` 执行显式编辑和模式位移，扫描 executor 做受限精修。schema 和例子见[能力图](references/capability_map.zh-CN.md)、[调用卡](references/call_cards.zh-CN.md)、[恢复手册](references/recovery_playbook.zh-CN.md)。编辑后、电子结构 Job 前运行 `geometry-preflight`，并把父 digest、键变化、姿态假设、约束和拒绝原因交给 `candidate-generation`。

## Further references

- [reactive geometry.zh CN](references/reactive_geometry.zh-CN.md)
