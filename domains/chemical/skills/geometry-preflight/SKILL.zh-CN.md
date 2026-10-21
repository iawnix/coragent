---
name: geometry-preflight
description: 在电子结构计算前筛查坐标，同时保留声明的非平衡反应中心几何。
---

# 几何预检

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#geometry-preflight)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** `chemical.geometry-safety@1` → `skills/geometry-preflight/scripts/run.py`。

Gaussian、xTB、CF22D、QST、NEB 或重启帧进入求解器前，对 XYZ 或 Gaussian 输入运行此检查。它捕获非有限坐标、原子数/标题不一致、核塌缩和严重的非反应短接触，同时允许 TS 种子中有意形成/断裂的键处于非平衡距离。

## profile 与输入

选择 `general`、`reaction_seed`、`ts_candidate` 或 `path_image`。知道反应上下文时提供从零开始的反应对索引，让检查器区分成键接触和意外碰撞。Gaussian 文本逐个检查显式 Cartesian 块；`Geom=AllCheck` 没有可检查坐标，会记录为未评估。

通过 `chemical.geometry-safety@1` 使用共享 `skills/_shared/geometry_safety.py`：

```text
--input <xyz-or-gjf> --output <report.json>
```

结果包含硬失败、警告、反应对豁免、profile 和 `safe`/`unsafe`/`not_assessed`。safe 只表示可以准备求解器输入，优化、模式、IRC 和结构评估仍由相应 Skill 完成。

schema、阈值和 Gaussian 块处理见[几何安全](references/geometry_safety.zh-CN.md)。`reactive-geometry` 编辑后再次运行，并把报告 digest 交给候选 Job。
