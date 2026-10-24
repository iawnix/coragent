---
name: gaussian
description: 准备和执行 Gaussian 的 XYZ 或显式输入 Job，解析原生日志并保留 route、电子态、能量、梯度和频率证据。
---

# Gaussian 后端

[English version](SKILL.md)

## 脚本路由

按 executor ID 查看[操作入口](references/commands.zh-CN.md)，再读取本 Skill 中对应的输入与验证合同。普通调用不需要阅读源码；`scripts/` 中未列出的文件是内部辅助模块。

Gaussian 用于优化、单点、QST/TS、频率、IRC、松弛扫描、电子态跟踪或最终日志证据时使用。本 Skill 负责 route、文件暂存、原生执行和解析；科学问题与验收标准由操作 Skill 决定。

## 已注册适配器

`chemical.gaussian@1`：XYZ 的 `sp/opt/opt-sp`；`chemical.gaussian-input@1`：完整 `.gjf/.com`，可做 QST、TS、频率、IRC、扫描和 Link1；`chemical.electronic-gaussian@1`：给定态的 `sp/opt`；`chemical.state-tracking@1`：电子态特征跟踪；`chemical.gaussian-evidence@1`：供 validation 使用的日志证据。路径梯度/NEB 位于 `candidate-generation`，鞍点/IRC 检查位于 `validation`。

上述计算应通过已注册适配器准备请求，再将该请求交给 `job_start`。`chemical.gaussian-input@1` 在准备阶段和 Gaussian 启动前分别检查显式输入；XYZ 快捷方式在运行时检查几何。软件/环境检查只确认 Gaussian 能运行，不代表新输入已通过检查。自定义多步流程中也应保留有检查的适配器调用，不要替换成未经检查的 `g16 < input.gjf` 脚本；文件准备、分析以及适配器范围以外的操作仍可使用通用 shell 工具。

## XYZ 快捷方式

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.gaussian --version 1 --input geometry=input.xyz --cpus 12 --job-memory-mb 16384 --output prepared/gaussian.json -- --task opt-sp --method M062X --basis '6-31G**' --charge 0 --multiplicity 1
```

`opt` 做几何优化，`sp` 做固定几何单点，`opt-sp` 两者都做。结果记录能量、收敛、优化几何、方法/基组、电子态、原生日志和解析摘要。

结合 `summary.optimization_completed` 与 `optimization_completion_reason` 读取优化状态。解析器识别 Gaussian 明确给出的可忽略力完成准则，同时保留原始四项收敛记录和更严格的 `final_convergence_satisfied` 标记。失败后从 `result.json.last_attempt` 和 `last_geometry.xyz` 检查最后结构、选择重启方案；随后按研究需要进行频率、模式和 IRC 检查。

## 显式输入

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --validation none
```

可用 `--validation opt|sp|frequency|minimum|saddle|irc` 选择计算输出的检查类型；`--validation none` 只是不选择这些任务特定的输出检查，不会关闭输入验证。输入要有完整 Link1 元数据和末尾空白段。QST2/QST3 使用 [candidate-generation](../candidate-generation/SKILL.zh-CN.md) 的 `chemical.qst-prepare@1` 序列化映射结构，每套结构都有独立的标题、电子态和坐标块。将生成的输入交给 `chemical.gaussian-input@1` 准备，再用 `job_start` 提交准备好的请求，随后检查 `gaussian.out`、`parsed.json`、checkpoint、几何和验证字段。

准备阶段检查 section 结构、QST 块、声明的电子态与资源，以及显式笛卡尔几何。输入被拒绝后应修正并重新准备，不要改成直接 shell 提交来绕过检查。检查通过不代表 TS 猜测在化学上合理；应复用已优化片段，在放置时保持片段内部几何，编辑后检查反应中心角度和接触，见[反应几何](../reactive-geometry/SKILL.zh-CN.md)。

route 与解析细节见 [L101 输入指南](references/l101_input_guide.zh-CN.md)、[电子态](references/electronic_states.zh-CN.md)、[松弛扫描](references/relaxed_scans.zh-CN.md)和 [Gaussian 验证](references/gaussian_validation.zh-CN.md)。

资源统一在 Job 准备阶段设置：`--cpus 12 --job-memory-mb 16384` 申请 12 核、16 GiB 总内存。省略的程序线程数跟随申请，Gaussian 的 `%mem` 会留出至少 256 MiB 且不少于总量 10% 的开销（此例为 14745 MiB）。显式 GJF 的 `%nprocshared`/`%mem` 会被读取但不改写；未指定作业资源时用于推导申请，已指定时检查线程冲突和内存余量。调整资源必须重新准备请求；默认值不是硬件上限。
