---
name: xtb
description: 运行 GFN2-xTB 单点和优化，并为扫描、梯度和路径搜索提供 xTB 计算器。
---

# xTB 后端

[English version](SKILL.md)

## 脚本路由

按 executor ID 查看[操作入口](references/commands.zh-CN.md)，再读取本 Skill 中对应的输入与验证合同。普通调用不需要阅读源码；`scripts/` 中未列出的文件是内部辅助模块。

xTB 适合快速构象精修、固定几何能量筛选、受限扫描、梯度计算和早期反应路径探索。明确电荷、多重度、溶剂和优化级别，使各阶段结果可比较。

## 注册包装器

`chemical.xtb@1` 从 XYZ 运行 GFN2-xTB 的 `sp`、`opt` 或 `opt-sp`。主要参数为 `--charge`、`--multiplicity`、`--opt-level normal|tight|verytight`、`--executable` 和 `--output-dir`。

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.xtb --version 1 --input geometry=input.xyz --output prepared/xtb.json -- --task opt-sp --charge 0 --multiplicity 1 --opt-level tight
```

结果包含要求时的优化几何、能量和收敛摘要、原生输出、电子态/溶剂字段和来源 digest。准备请求并用 `job_start` 标准 Job 生命周期执行，检查解析摘要后再交给下一步。

## 反应路径操作

`chemical.scan-xtb@1` 是 `candidate-generation` 和 `reactive-geometry` 使用的受限扫描/预优化计算器；`chemical.gradient-xtb@1` 提供梯度；`chemical.neb-xtb@2` 通过 ASE NEB v2 使用 path_xTB。它们保留约束、帧和端点元数据。xTB 适合宽搜索，重要候选再用 CF22D 或 Gaussian 精修。

字段和原生输出解析见 [xTB 执行器](references/xtb_executor.zh-CN.md)与[后端合同](references/xtb_backend_contract.zh-CN.md)。其它原生功能可通过 generic Job 配置控制文件和收集输出。
