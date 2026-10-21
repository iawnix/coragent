---
name: energetics
description: 根据相容的计算结果计算电子能、热校正、自由能、反应能、势垒、集合能量和有限范围动力学量。
---

# 能量学与动力学

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#energetics)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.thermochemistry@1` → `skills/energetics/scripts/energy.py`；`chemical.ensemble-free-energy@1` → `skills/energetics/scripts/energy.py`；`chemical.energy-profile@1` → `skills/energetics/scripts/energy.py`；`chemical.scan-slice@1` → `skills/energetics/scripts/energy.py`；`chemical.tst@1` → `skills/energetics/scripts/energy.py`；`chemical.branching@1` → `skills/energetics/scripts/energy.py`；`chemical.kinetic-network@1` → `skills/energetics/scripts/energy.py`。

在结构和电子结构结果收集完成后使用本 Skill。它把相容的能量和频率转成热化学、反应/活化能剖面、构象人口、条件 TST 速率、分支估计和显式动力学网络轨迹。

## 计算流程

1. 对每个物种收集电子能；需要时再收集同一几何、原子顺序、方法、电荷、多重度、溶剂和标准态下的频率/热化学结果。
2. 用 `chemical.thermochemistry@1` 组合电子能、零点能、热焓、熵和 Gibbs 自由能。记录温度、压力或浓度标准态，以及低频模式处理方式。
3. 对构象或复合物集合使用 `chemical.ensemble-free-energy@1`，按声明的人口模型计算集合自由能和成员权重。
4. 对反应物/中间体/TS/产物离散状态使用 `chemical.energy-profile@1`；对坐标网格使用 `chemical.scan-slice@1`。明确计量和参考态。
5. 对已有频率处理的候选使用 `chemical.tst@1`；对共享前体的路径用 `chemical.branching@1`；对给定速率常数和初始浓度的质量作用网络用 `chemical.kinetic-network@1`。

## 数值含义

电子反应能是 dE，加 ZPE 得到 d(E+ZPE)，加入热焓得 dH，标准态 Gibbs 值给出 dG。势垒使用同一参考：Ea = E_TS - E_R，dG‡ = dG_TS - dG_R。按结果中的单位字段在 Hartree、kcal/mol、kJ/mol 间转换。气相 1 atm、溶液 1 M 等标准态必须明确记录。

构象集合存在多个有占比成员时，使用人口加权自由能。TST 和分支结果同时报告假设与前体范围；剖面或扫描切片记录采样状态，IRC/validation 记录连通性，`report` 负责展示。

## 已注册脚本与合同

适配器位于 `skills/energetics/scripts/energy.py` 和 `thermochemistry.py`；CLI 的 operation 可选 `thermochemistry`、`ensemble`、`profile`、`scan-slice`、`tst`、`branching`、`network`，并接收 `--input` 与 `--output-dir`。结果含可追溯 JSON/CSV 并保留缺失值。比较路径前阅读[能量执行合同](references/energy_execution.zh-CN.md)、[科学检查](references/energetics.zh-CN.md)和[动力学执行合同](references/kinetics_execution.zh-CN.md)。
