---
name: method-selection
description: 根据目标观测量、体系、电子态、环境和不确定性预算选择科学方法与执行后端。
---

# 方法与后端选择

[English version](SKILL.md)

## 脚本路由

按 executor ID 使用[脚本路由地图](../../../../docs/skill-script-routing.zh-CN.md#method-selection)选择入口、CLI、输入和主要输出。地图是路由依据；`scripts/` 下的 helper 不是独立命令。不要通过读取源码发现调用方式，先读操作合同，只有合同未说明的选项才使用 executor 的 `--help`。

**入口：** 无仓库内脚本；按文档使用 runtime 或 generic Job。

需要选方法、比较方法或在命名计算环境中准备固定方法时使用。本 Skill 从研究需要的量开始，把方法选择写入研究 Node 和 Job intent。

## 选择流程

1. 写明目标观测量：几何、相对能、势垒、频率、IRC、自旋交叉或动力学。
2. 记录体系大小、电荷、多重度、溶剂、约束、柔性、金属/多参考迹象，以及精度和成本预算。
3. 选择探索层和精修层。常见组合是 CREST/xTB 做构象和姿态，xTB/CF22D 做筛选和梯度，Gaussian 或声明的高层方法做最终 TS/频率证据。
4. 用[操作/后端图](references/operation_backend_map.zh-CN.md)和[注册表](references/operation_backend_registry.zh-CN.md)把操作映射到后端，保持操作、后端和证据的职责分开。
5. 用 `job_probe` 检查命名环境，用方法 Skill 准备 executor 请求，再启动、提交和收集 Job。
6. 方法矩阵先展开每个“方法 × 环境 × 操作”单元再启动；每个不可用单元独立记录，成功单元保持可比较设置。
7. 搜索失败时区分环境、输入、数值和假设问题，按[搜索恢复](references/search_recovery.zh-CN.md)改变下一动作。

## 实用组合

用 xTB/CREST 探索构象、片段姿态、扫描和宽泛路径候选；需要一致 PySCF 方法时用 CF22D 做筛选、优化、频率或有限 TS 搜索；需要显式 route、QST/TS/频率/IRC 和原生日志证据时用 Gaussian。未注册后端通过 generic Job 并声明输入输出。

方法选择属于科学结果的一部分：记录基组、色散、溶剂、电子态、温度、约束、可执行文件版本和环境。端点与 TS 的设置匹配后再比较能量或频率。证据要求由 `candidate-generation`、`validation`、`energetics` 等操作 Skill 决定。

科学判据、后端合同、运行时诊断和请求准备见 [method_selection.zh-CN.md](references/method_selection.zh-CN.md)、[backend_contract.zh-CN.md](references/backend_contract.zh-CN.md)、[runtime_environment.zh-CN.md](references/runtime_environment.zh-CN.md) 和 [request_preparation.zh-CN.md](references/request_preparation.zh-CN.md)。

## Further references

- [capabilities.zh CN](references/capabilities.zh-CN.md)
- [job probes.zh CN](references/job_probes.zh-CN.md)
- [runner results.zh CN](references/runner_results.zh-CN.md)
- [xtb operation recipes.zh CN](references/xtb_operation_recipes.zh-CN.md)

在昂贵的 TS、IRC 或多点搜索前，明确探索层、精修层以及候选晋级依据。柔性体系和分离片段优先考虑适用的 xTB/CREST 构象或姿态探索；跳过时说明原因和有界替代方案。最终 DFT 方法要求不等于所有几何探索都必须使用 DFT，低层路径不能替代最终高层连通证据。
