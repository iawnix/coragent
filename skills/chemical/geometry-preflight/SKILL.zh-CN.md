---
name: geometry-preflight
description: 在电子结构计算前筛查坐标，同时保留声明的非平衡反应中心几何。
---

# 几何预检

[English version](SKILL.md)

## 脚本路由

按 executor ID 查看[操作入口](references/commands.zh-CN.md)，再读取本 Skill 中对应的输入与验证合同。普通调用不需要阅读源码；`scripts/` 中未列出的文件是内部辅助模块。

Gaussian、xTB、CF22D、QST、NEB 或重启帧进入求解器前，筛查候选坐标。独立执行器接受 `chemical-geometry-safety-input/1` JSON，其中包含元素、以 Å 为单位的笛卡尔坐标，以及已知的反应和成键关系；不直接接受 XYZ 或 GJF 文件。它捕获非有限坐标、原子数与坐标数不一致、核塌缩和严重的非反应短接触，同时允许 TS 种子中有意形成/断裂的键处于非平衡距离。

## profile 与输入

在 JSON 中选择 `general`、`reaction_seed`、`ts_candidate` 或 `path_image`。知道反应上下文时提供从零开始的反应对索引，让检查器区分成键接触和意外碰撞。检查编辑后的姿态时，提供已知成键对与参考坐标；缺少连接关系或参考结构时，诊断范围有限。

将[几何安全](references/geometry_safety.zh-CN.md)中的 JSON 保存为 `<work_dir>/geometry-check.json`，然后准备 `chemical.geometry-safety@1`：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.geometry-safety --version 1 --input "input=<work_dir>/geometry-check.json" --output "<work_dir>/prepared/geometry-check.json"
```

使用 `research_create` 或 `research_read` 返回的实际工作目录。准备器返回 `request_file` 和 `request_sha256`；此时尚未执行独立检查。用返回值提交：

```text
job_start({"node_id":"<node_id>","request_file":"<returned request_file>","request_sha256":"<returned request_sha256>"})
```

读取完成 Job 的 `results/result.json`。报告包含 `safe`/`unsafe`、硬失败、警告，以及可能为 `not_assessed` 的分项状态。检查 Job 完成也可能得到 `unsafe`，使用候选前必须读报告。`safe` 仅表示没有命中已覆盖的硬失败，不证明角度具有化学合理性、结构身份正确、求解器能够收敛或已经得到有效 TS。

显式 Gaussian 输入使用 [Gaussian Skill](../gaussian/SKILL.zh-CN.md)：`chemical.gaussian-input@1` 在请求准备时以及启动 Gaussian 前检查显式 Cartesian 块。`Geom=AllCheck` 没有文本坐标可检查，需要单独检查来源检查点中的结构。通用 Bash 执行不会应用这些 Gaussian 检查。

字段、阈值和覆盖范围见[几何安全](references/geometry_safety.zh-CN.md)。`reactive-geometry` 编辑后重新检查坐标，保留报告作为候选证据。摆放反应物时保留优化片段的内部几何，不要为了对齐转移坐标而拉直片段内部的键角。
