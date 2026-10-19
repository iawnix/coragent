---
name: gaussian
description: 准备和执行 Gaussian 的 XYZ 或显式输入 Job，解析原生日志并保留 route、电子态、能量、梯度和频率证据。
---

# Gaussian 后端

[English version](SKILL.md)

Gaussian 用于优化、单点、QST/TS、频率、IRC、松弛扫描、电子态跟踪或最终日志证据时使用。本 Skill 负责 route、文件暂存、原生执行和解析；科学问题与验收标准由操作 Skill 决定。

## 已注册适配器

`chemical.gaussian@1`：XYZ 的 `sp/opt/opt-sp`；`chemical.gaussian-input@1`：完整 `.gjf/.com`，可做 QST、TS、频率、IRC、扫描和 Link1；`chemical.electronic-gaussian@1`：给定态的 `sp/opt`；`chemical.state-tracking@1`：电子态特征跟踪；`chemical.gaussian-evidence@1`：供 validation 使用的日志证据。路径梯度/NEB 位于 `candidate-generation`，鞍点/IRC 检查位于 `validation`。

## XYZ 快捷方式

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian --version 1 --input geometry=input.xyz --output prepared/gaussian.json -- --task opt-sp --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 8 --memory-mb 8000
```

`opt` 做几何优化，`sp` 做固定几何单点，`opt-sp` 两者都做。结果记录能量、收敛、优化几何、方法/基组、电子态、原生日志和解析摘要。

## 显式输入

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 12 --memory-mb 4000 --validation none
```

可用 `--validation opt|sp|frequency|minimum|saddle|irc` 选择解析检查。输入要有完整 Link1 元数据和末尾空白段。用 `job_start` 提交后检查 `gaussian.out`、`parsed.json`、checkpoint、几何和验证字段。

route 与解析细节见 [L101 输入指南](references/l101_input_guide.zh-CN.md)、[电子态](references/electronic_states.zh-CN.md)、[松弛扫描](references/relaxed_scans.zh-CN.md)和 [Gaussian 验证](references/gaussian_validation.zh-CN.md)。
