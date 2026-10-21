---
name: surface-crossing
description: 使用能隙、投影梯度和 seam 曲率证据搜索并检查不同自旋 Gaussian 交叉候选。
---

# 不同自旋表面交叉

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#surface-crossing)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.mecp-gaussian@1` → `skills/surface-crossing/scripts/crossing.py`；`chemical.crossing-check@1` → `skills/surface-crossing/scripts/crossing.py`。

研究两个不同自旋多重度 Gaussian HF/DFT 表面的交叉时使用。原生搜索为 `chemical.mecp-gaussian@1`，独立数值证据为 `chemical.crossing-check@1`。

## 工作流

1. 准备含两个态定义、电荷、多重度、起始几何、Gaussian 方法/基组和收敛设置的输入。
2. 在 path_gaussian 环境运行 `chemical.mecp-gaussian@1`，保留候选几何、态能量、梯度、投影梯度范数、能隙和收敛记录。
3. 对收集的候选运行 `chemical.crossing-check@1`，一起检查能隙、投影梯度和可选约束 seam 曲率。
4. 把态特征连续性和 SCF 稳定性与 seam 数值证据比较。若几何有有用的交叉方向，可带着交叉上下文交给 `candidate-generation` 或 `validation`。

检查器使用 `structure` binding 和普通 Job。schema 与阈值见[交叉执行合同](references/crossing_execution.zh-CN.md)。小能隙只是筛选信号，交叉决定要结合梯度/曲率和态记录。
