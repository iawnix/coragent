---
name: reaction-investigation
description: 从物种和机理假设开始，经过候选搜索、验证、能量学、恢复和证据结论，执行闭环反应研究。
---

# 反应研究

[English version](SKILL.md)

进行反应机理或过渡态研究时使用本 Skill。它协调领域 Skills，并保持一条化学决策闭环：定义假设、准备材料、构建候选、运行计算、验证证据、比较能量，再选择能区分假设的下一项实验。

## 工作流合同位置

工作流合同位于 [references/reaction_investigation.zh-CN.md](references/reaction_investigation.zh-CN.md)，英文版在同目录。它放在本 Skill 内，因为它描述反应研究的状态机和交接；通用 CoRAgent runtime 只保存 Node、Job、Artifact 和证据。

每个基元步骤都维护物种身份、原子映射、电荷、多重度/电子态、环境、键变化、候选几何、验证状态、能量状态和下一项未解决问题。计算只有在读取输出并把它转成记录中的观察或决定后才算完成。

## 闭环步骤

1. **定义**：写明反应物/产物、可能中间体、键变化、立体化学结果和竞争机理，并列出可区分它们的预测。
2. **准备**：用 `material-preparation` 解析名称/SMILES，保留给定坐标，生成缺失种子并建立反应原子映射。
3. **评估**：用 `structure-assessment` 和 `geometry-preflight` 检查图、片段、电子态、接触和反应中心几何。
4. **构建**：用 `reactive-geometry` 生成接近姿态，用 `candidate-generation` 选择 QST、扫描、直接 TS 或 NEB。位点/进攻面/构象未区分时保留多个假设。
5. **运行与验证**：用 `method-selection` 选择后端，运行 Gaussian/xTB/CF22D，再用 `validation` 获取模式和 IRC 证据。
6. **比较**：用 `energetics` 计算相容的 E/ZPE/H/G、势垒、集合人口、TST、分支或动力学网络。
7. **恢复或结论**：失败时依据失败模式改变构造/搜索动作；成功时引用全部来源 Artifact、竞争解释和不确定性，发布结果和下一项实验。
8. **交付**：用 `report` 生成表格、图、轨迹和可读证据包。

对显式多步路径可用 `chemical.pathway-check@1` 做独立审查，脚本为 `skills/reaction-investigation/scripts/pathway_job.py`。反应研究闭环仍由本 Skill 协调。

## 决策习惯

把物种身份、基元步骤连通性、鞍点证据、能量学、动力学和稳健性分开记录。失败搜索若揭示姿态、端点、电子态或机理错误，应保留并用于改变下一步。机理结论来自多条记录的收敛证据，而不是单个成功 Job。

多步或竞争解释研究可阅读[路径模型](references/pathway_model.zh-CN.md)、[分子准备](references/molecular_preparation.zh-CN.md)、[路径执行](references/pathway_execution.zh-CN.md)和[机理反思](references/mechanism_reflection.zh-CN.md)。

## Further references

- [strategy reflection.zh CN](references/strategy_reflection.zh-CN.md)
