---
name: mechanism-reasoning
description: 协调反应路径与过渡态研究，从输入和机理假设推进到候选搜索、验证、失败恢复及有证据支持的结论。
---

# CoRAgent 反应机理思考

[English version](SKILL.md)

反应机理或过渡态研究（包括恢复未完成搜索）使用本 Skill。它负责跨操作 Skill 的科学计划：
识别下一项未解决问题，选择可区分假设的计算，检查证据，并将结果带入下一步决策。
也可单独用于机理推理；概念性问题不要求运行计算。

计算任务先读[反应研究闭环](references/reaction_investigation.zh-CN.md)。交给 chemical-input、
reactive-geometry、candidate-generation、validation、energetics 或 report 时，仍负责决定下一步。
这些 Skill 是同一 Agent 使用的方法说明，不是独立 Agent 或自动工作流。
通用运行时保存任务、Job 与证据，不选择化学前置条件，也不判定机理是否成立。

显式定义物种、组成、电荷、自旋或电子态、原子映射、成键变化、环境与可逆性。在 Node 的 proposal 中写明机理假设，在 plan 中描述预测与可证伪观察；结果中的支持或冲突用 conclusion 和证据说明。需要独立比较的方案可用 alternative_to 关联。研究依赖不表示化学连通性。

在研究笔记中明确检查标准、支持证据、未解决问题和下一步，引用实际收集的材料。计算完成不能代替对科学结论的判断。

将物种身份、基元步骤连通性、鞍点证据、能量学、动力学与稳健性拆成可以独立失败的问题。
保留竞争机理与意外结果。证据挑战当前问题框架时，修订当前 Node 的思路；独立新问题才创建相关 Node，不改写既有结果。

## 参考资料

- 物种、映射与输入准备见
  [reaction_mapping.zh-CN.md](../chemical-input/references/reaction_mapping.zh-CN.md) 和
  [molecular_preparation.zh-CN.md](references/molecular_preparation.zh-CN.md)。
- 路径假设与化学连通性见 [pathway_model.zh-CN.md](references/pathway_model.zh-CN.md)。
- 可区分假设与 falsifier 见
  [mechanism_reflection.zh-CN.md](references/mechanism_reflection.zh-CN.md)。
- 重复或意外结果后的重新框定见
  [strategy_reflection.zh-CN.md](references/strategy_reflection.zh-CN.md)。

条件化探索决策与多步材料见[路径检查合同](references/pathway_execution.zh-CN.md)。
chemical.pathway-check@1 使用 structure 环境与 input 角色，保留假设、产物猜测、
观察、原子/计量连续性和缺失步骤。可选绑定的经典模式/IRC 证据会重新检查，缺证据
不会变成通过。竞争产物用 energetics Skill 分开比较热力学、条件 TST 分支与显式可逆网络。
