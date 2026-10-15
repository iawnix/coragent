---
name: xtb
description: 将已声明的 xTB 输入、原生命令和解析证据适配到注册的 xTB 绑定，不选择科学操作。
---

# xTB 后端

本 Skill 负责 xTB 命令绑定、输入暂存、电子态/溶剂字段转换和受支持的输出解析。它不在筛选、
优化、扫描、动力学或路径操作之间做科学选择，也不认证过渡态或解释研究结果；这些决策属于
操作 Skill 和 `method-selection`。

`chemical.xtb@1` 是 GFN2-xTB 的注册封装，支持 `sp`、`opt`、`opt-sp`。它把电荷和多重度
转换为原生命令，记录请求的溶剂/态字段，并返回原始输出来源：

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.xtb --version 1 --input geometry=input.xyz --output prepared/xtb.json -- --task opt-sp --charge 0 --multiplicity 1
```

其它原生 xTB 命令通过通用 Job、显式控制文件和收集输出执行；使用 `job_start` 启动作业，
原生命令选项不是封装器的 `--task` 值。解析字段和回执见 [xTB 后端合同](references/xtb_backend_contract.zh-CN.md) 及[共享 runner 合同](../method-selection/references/runner_results.zh-CN.md)。

基于材料的有界扫描和 Cartesian 梯度在 `candidate-generation` 注册为
`chemical.scan-xtb@1`、`chemical.gradient-xtb@1`；可选的 `path_xtb` 绑定也服务于
`chemical.neb-xtb@2`。这些入口负责操作层的约束、梯度和 NEB 证据；本 Skill 只提供 xTB
适配器和解析边界。旧的[xTB 执行指针](references/xtb_executor.zh-CN.md)为现有链接保留。
