---
name: surface-crossing
description: 搜索并检查两个不同自旋 Gaussian HF/DFT 表面的规则交叉，核对能隙、投影梯度与可选交叉缝曲率。
---

# 不同自旋表面交叉

[English](SKILL.md)

使用 `chemical.mecp-gaussian@1` 做有界交叉候选搜索，使用
`chemical.crossing-check@1` 独立核对数值证据。先阅读
[执行合同与科学范围](references/crossing_execution.zh-CN.md)。原生求解采用可选
`path_gaussian` 绑定；检查器使用 `structure`。均以 `input` 输入角色执行普通 Job。

小能隙本身不足以证明 MECP：还需检查投影梯度与约束曲率。数值交叉缝驻点与态身份、
SCF 稳定性、全局最优须分别说明。多重度不同且 S² 合理，也不能证明波函数连续。
本实现不是 QBICS，不支持同自旋圆锥交叉、旋轨耦合或非绝热动力学，也不能以普通
TS/IRC 验证器代替专用交叉检查。
