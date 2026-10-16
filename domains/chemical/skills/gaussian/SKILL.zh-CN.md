---
name: gaussian
description: 将已声明的 Gaussian 输入和计算适配到注册的 Gaussian 绑定，保留 route、电子态、解析器和来源合同。
---

# Gaussian 后端

本 Skill 负责 Gaussian route 构造、输入暂存与执行、原始日志解析以及受支持的能量/梯度
证据。它不选择科学操作、不为研究问题选择方法、不归属 IRC 势阱，也不认证过渡态；这些
决策分别属于 `candidate-generation`、`validation` 和 `method-selection`。

已注册的适配器：

- `chemical.gaussian@1` 接受材料 XYZ，支持 `sp`、`opt`、`opt-sp` runner 任务。
- `chemical.gaussian-input@1` 接受完整 `.gjf`，用 `--validation opt/sp/frequency/minimum/saddle/irc/none`
  检查声明的 route。
- `chemical.electronic-gaussian@1` 和 `chemical.state-tracking@1` 提供[电子态合同](references/electronic_states.zh-CN.md)。
- `chemical.gaussian-evidence@1` 将选定的原始日志 section 规范化，供独立 validation 和 IRC 检查使用。

两个执行适配器都使用目标 `gaussian` 绑定。适配器负责暂存输入和依赖、保留电荷/多重度及
方法元数据、记录原始输出并返回解析证据；Job 成功不会自动附加科学结论。

XYZ 适配器通过 executor 接口准备 Job：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian --version 1 --input geometry=input.xyz --output prepared/gaussian.json -- --task opt-sp --charge 0 --multiplicity 1
```

显式输入的 checkpoint 依赖使用 Job 内相对名称暂存，并保留 section 结束空行：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 12 --memory-mb 4000 --validation none
```

这些命令只准备请求；使用 `job_start` 启动作业，再按[共享 runner 合同](../method-selection/references/runner_results.zh-CN.md)提交和收集。研究
Job 不应直接调用 Gaussian。显式输入解析器要求完整的 Link1 元数据、相对暂存依赖和末尾空行；
L101 解析错误见 [L101 输入文件说明](references/l101_input_guide.zh-CN.md)。

解析器区分受支持的参考 SCF 能量，并将不支持或不完整的证据明确记录。`--validation none` 只
关闭 runner 检查，不扩大解析范围。科学结论使用操作 Skill 的证据检查。Gaussian 路径梯度和
NEB 使用 `candidate-generation` 下独立的 `path_gaussian` 适配器。直接使用 Gaussian 验证和扫描说明，见[validation 所有的 Gaussian 检查](references/gaussian_validation.zh-CN.md)和[Gaussian 扫描配方](references/relaxed_scans.zh-CN.md)。
