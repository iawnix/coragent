---
name: cf22d
description: 将已声明的 CF22D/PySCF 输入和解析证据适配到注册的 pyscf 绑定，不选择或验证科学任务。
---

# CF22D 后端

本 Skill 负责 CF22D/PySCF 绑定、任务参数转换、输入暂存、单位和解析证据。它不为研究问题
选择基组或科学操作，也不认证驻点、过渡态或热化学；这些决策属于 `method-selection`、
`candidate-generation`、`energetics` 和 `validation`。

`chemical.cf22d@1` 接受 `sp`、`opt`、`opt-sp`、`ts`、`freq`、`thermo`、`opt_freq`、
`ts_freq` 任务词汇。目标 `pyscf` 环境必须提供 CF22D 及声明的色散实现。适配器按[共享 runner 合同](../method-selection/references/runner_results.zh-CN.md)
记录基组、电荷、多重度、任务、收敛字段、单位和原始来源。

通过 executor 接口准备请求：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.cf22d --version 1 --input geometry=input.xyz --output prepared/cf22d.json -- --task opt-sp --basis def2-tzvp --charge 0 --multiplicity 1
```

请求文件不是结果；使用 `job_start` 启动作业，再通过标准 Job 生命周期提交和收集。环境前置条件与解析字段见
[CF22D 工作流](references/cf22d_workflow.zh-CN.md)和[环境诊断](references/environment_doctor.zh-CN.md)。
