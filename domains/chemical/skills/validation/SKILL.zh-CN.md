---
name: validation
description: 为过渡态候选建立鞍点、振动模式、电子态、结构和 IRC 证据。
---

# 过渡态验证

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#validation)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.path-irc@1` → `skills/validation/scripts/irc_preparation.py`；`chemical.stationary-check@1` → `skills/validation/scripts/evidence_check.py`；`chemical.mode-check@1` → `skills/validation/scripts/evidence_check.py`；`chemical.irc-check@1` → `skills/validation/scripts/evidence_check.py`；`chemical.gaussian-evidence@1` → `skills/validation/scripts/evidence_check.py`。

候选生成和实际 TS 优化或路径搜索完成后使用本 Skill。它把一个候选的独立证据组合成决定：已验证鞍点、需要指定检查的候选，或带下一步搜索动作的失败。

## 验证顺序

1. **求解器证据**：读取主输出，确认正常结束、优化收敛、电荷/多重度、方法和几何 digest。
2. **驻点**：用 `chemical.stationary-check@1` 或 `chemical.gaussian-evidence@1` 检查最终梯度/Hessian 字段和驻点记录。
3. **模式**：用 `chemical.mode-check@1` 检查频率和振动向量。经典一级鞍点应有一个相关虚频，其位移沿着假设的成键/断键、原子转移或扭转坐标。
4. **结构与电子态**：对照反应假设检查原子映射、组成、立体化学、关键距离、自旋/电子态和模式方向。
5. **连通性**：用 `chemical.path-irc@1` 准备正反 IRC，执行声明的 IRC 计算，再用 `chemical.irc-check@1` 将端点与选定反应物/产物 Artifact 比较。
6. **决定**：记录满足的标准、未解决证据、来源 Artifact 和改变后的下一操作。模式正确但到达错误盆地时，返回候选生成并修正端点或几何。

## 已注册检查

`chemical.stationary-check@1` 检查驻点和结束字段；`chemical.mode-check@1` 检查虚频数量、大小和与反应坐标的对应；`chemical.gaussian-evidence@1` 规范化 Gaussian 输出；`chemical.path-irc@1` 从 checkpoint 准备正反 IRC；`chemical.irc-check@1` 检查路径完整性与端点。

独立检查应作为证据记录，并结合主输出阅读。把执行失败、证据不可读和检查完成但未满足标准分开记录。每个 IRC 分支保留来源鞍点、方向、路径 Artifact、端点 Artifact 和 digest。

详见[过渡态验证](references/transition_state_validation.zh-CN.md)、[IRC 验证](references/irc_validation.zh-CN.md)、[连通性验证](references/connectivity_validation.zh-CN.md)、[结构验证](references/structure_validation.zh-CN.md)，候选与验证的交接合同见[reaction task interface](../candidate-generation/references/reaction_task_interface.zh-CN.md)。

## Further references

- [gaussian validation.zh CN](references/gaussian_validation.zh-CN.md)
- [general checks.zh CN](references/general_checks.zh-CN.md)
- [irc preparation.zh CN](references/irc_preparation.zh-CN.md)

IRC 验收分别报告路径完整性、映射化学身份、端点极小点与构象差异。全体系 RMSD 是构象诊断，不作为化学身份门槛；分离片段的相对取向变化不能否决物种身份。声明的键连与立体化学仍须由实际端点几何支持。
