---
name: energetics
description: 评估电子能、ZPE 与热校正、自由能和反应能、势垒、有限范围的 TST 速率及能量剖面。
---

# CoRAgent 能量学

[English version](SKILL.md)

使用本 Skill 处理 `E`、`E+ZPE`、`H`、`G`、反应能与活化能、标准态校正、有限范围的
过渡态理论速率和能量剖面。必须明确能量类型、单位、温度、压力或浓度、标准态、相态、
溶剂、方法、电子态、化学计量与频率处理。

只有结构、原子顺序、方法和声明的组合处理一致时，才能组合电子与热结果。不要用电子
势垒替代 Gibbs 势垒，不要推断未支持的同位素校正，也不要把定性路径枚举当作动力学。
数值与局限应分别记录为引用来源 Artifact 的研究记录。

使用 `chemical.thermochemistry@1`、`chemical.ensemble-free-energy@1`、
`chemical.energy-profile@1`、`chemical.scan-slice@1`，通过普通 Job、输入角色
`input` 和 `structure` 环境执行。准备输入前阅读
[执行合同与数值范围](references/energy_execution.zh-CN.md)。输出可追溯 JSON/CSV，
保留缺失值，拒绝不一致来源、条件和计量。目前这些分析执行器只接受明确基态。

结果解释见[科学检查](references/energetics.zh-CN.md)。使用 chemical.tst@1、chemical.branching@1、chemical.kinetic-network@1
执行[条件速率、分支与显式质量作用网络](references/kinetics_execution.zh-CN.md)，比较路径前
核对其适用假设。离散剖面和扫描切片不能证明完整 PES、TS 连通性或自由能采样。
本地确定性合同及 Job 验证不代表真实求解器科学精度基准。
