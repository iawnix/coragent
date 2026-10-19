---
name: cf22d
description: 通过 PySCF 绑定运行 CF22D，支持单点、优化、频率、热化学和有限范围的过渡态搜索。
---

# CF22D 电子结构后端

[English version](SKILL.md)

选定 CF22D 作为电子方法时使用本 Skill。它把 XYZ material 和明确的电子设置交给注册的 PySCF/CF22D runner，并返回几何、能量、梯度、频率及任务提供的热化学字段。

## 任务类型

`chemical.cf22d@1` 支持：`sp`（给定几何的能量/梯度）、`opt`（几何优化）、`opt-sp`（优化后单点）、`ts`（初始 Hessian TS 优化）、`freq`（频率）、`thermo`（热量）以及 `opt_freq`、`ts_freq`。极小点用 `opt/opt_freq`，TS 候选用 `ts/ts_freq`，固定几何比较用 `sp`，几何和电子态确定后再做 `freq/thermo`。

## 输入设置

提供 angstrom XYZ、基组（默认 `def2-tzvp`）、电荷、多重度 `2S+1`、交换相关标签、网格级别、SCF 收敛阈值、最大循环/步数、温度、压力、线程和内存。端点、候选和频率 Job 应保持一致的电荷/多重度，除非研究确实包含电子态变化。色散和 CF22D 设置会写入结果，便于检查能量可比性。

## 典型请求

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.cf22d --version 1 --input geometry=input.xyz --output prepared/cf22d.json -- --task opt-sp --basis def2-tzvp --charge 0 --multiplicity 1 --threads 8 --memory-mb 8000
```

准备后用 `job_start` 启动，再提交和收集 Job。结果包括 `results/result.json`、`results/geometry.xyz`、任务输出、单位、收敛字段和原始来源。环境诊断使用 `chemical.cf22d-doctor@1`。

## 实际用法

当基组、电子态和收敛设置可控时，用 CF22D 做一致的筛选和几何精修。TS 工作先从 `candidate-generation` 得到化学上合理的候选，再运行 `ts` 并交给 `validation`。势垒或自由能计算则把相容的 CF22D 能量和频率结果交给 `energetics`。

任务 schema 和结果文件见 [CF22D 工作流](references/cf22d_workflow.zh-CN.md)、[环境诊断](references/environment_doctor.zh-CN.md)和[共享 runner 合同](../method-selection/references/runner_results.zh-CN.md)。
