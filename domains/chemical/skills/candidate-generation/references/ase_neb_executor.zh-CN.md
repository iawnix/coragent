# ASE NEB 候选搜索

[English](ase_neb_executor.md)

新搜索使用 `chemical.neb-xtb@2` 或 `chemical.neb-gaussian@2`。由 ASE 3.29.0
提供 improved-tangent NEB、climbing image 和 FIRE（默认）/BFGS 优化。
Calculator 接入已有核验接口：xTB 6.7.1 GFN1/GFN2（气相/ALPB），以及 Gaussian
指定自旋基态 HF/DFT（气相）。范围为非周期分子、单势能面；不覆盖激发态 NEB 或跨态搜索。
ASE 是唯一 NEB 实现。旧版本 1 执行入口已删除，旧请求须按版本 2 字段和单位重新准备。

## 准备与独立调用

选择已优化且构象相容的端点，并记录尚未解决的端点问题。核对显式 H 映射、电荷、
多重度与片段运动。只有反应物时先提出候选机制/产物；跨多步的 R/P 应先拆分为合理的
基元步骤。执行器固定给定端点，不替用户优化或认证端点。

配置原生 `path_xtb` 或 `path_gaussian` 后安装 `--job-profile local:path`。
独立 `path.lock` 含 ASE、SciPy、RDKit、NumPy；旧 wrapper/structure 不自动获得 ASE。
执行前检查所选环境、executor 和 version。

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.neb-xtb --version 2 --input input=<work_dir>/neb.json --input-artifact <input-ref> --output <work_dir>/neb-request.json
```

占位符替换为真实绝对路径/Artifact 引用，随后通过 job_start 提交返回的
request_file/request_sha256 与 node_id，结束后 job_collect。失败和达到上限也收集。
Gaussian 更换 executor 和 settings 即可，无需 ASE 服务，不改变 Task/Node/Job/Artifact。

## 输入合同

`chemical-neb-input/2` 内嵌 `reactant`、`product`（chemical-material/1）、从反应物
ID 到产物 ID 的完整 `mapping` 和原生 `settings`。2–256 个普通质量原子、Å 坐标、
已知电荷/多重度和明确相容 ground 态；产物按反应物 ID 重排。
材料与 xTB 设置见[路径合同](path_search.zh-CN.md)，Gaussian 使用
[电子态设置](../../gaussian/references/electronic_states.zh-CN.md)的 theory=ground、
functional/basis、自旋策略和资源限制。不自动解析名称、寻找映射、对齐片段或推断图。

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| image_count | 7 | 含端点共 3–32 个 image |
| images | 无 | 显式 image × atom × xyz 数组，按反应物顺序；首尾须匹配端点 |
| interpolation | linear | linear/idpp；已给 images 时禁止重新插值 |
| idpp_steps | 100 | 1–1000 次有界 IDPP 初始化，不是化学优化 |
| optimizer | FIRE | FIRE/BFGS |
| max_steps | 200 | 0–2000 次更新，0 仍评价初始路径 |
| max_evaluations | 10000 | 全路径共 1–100000 次原生求值尝试，失败也计数 |
| fmax_ev_per_angstrom | 0.05 | 正数，内部 image 最大逐原子 NEB 力范数 |
| spring_ev_per_angstrom2 | 0.1 | 正弹簧常数 |
| max_step_angstrom | 0.05 | 优化器步长上限，正数且不超过 1 Å |
| climb_after | 5 | 从 0 起计的激活轮次，0–2000；null 关闭爬山 |

普通 band 提前收敛时立即激活已请求的爬山并重新检查；激活后保持，切换时重建优化器。
IDPP 达到预算不认证其初始化已最优；初始碰撞和重复相邻 image 会被拒绝，必要时自行
提供合理路径。数值路径收敛不等于 TS 验证。

每个 image 独立 ASE Calculator，原生求值串行；单次求解器可按配置多线程。
核验几何、顺序、方法和收敛后，把 hartree 能量及 hartree/Å 的负梯度转换为 ASE 的
 eV 和 eV/Å；缓存避免重复计算未移动的端点/image。综合考虑单次 timeout、总求值预算
及 Job walltime。v2 不接受旧 fmax、spring、step_size、max_displacement 字段。

## 输出与后续

`chemical-neb-result/2` 记录 ASE 版本、参数、映射、模型、逐轮能量/NEB 力/爬山
和求值数。产物含 evaluations.json、逐轮 path.traj/path.xyz，以及最后完整已求值的
path.xyz、candidate.xyz、candidate.material.json（有完整路径时）。各次原生输入、
日志和计算证据均保留；ledger 在原生调用前写入，包含失败尝试。

只有 converged 退出零；step_limit/failed 保留部分证据及最后一轮**完整求值**的
结构—能量配对，未完成的新坐标另存。硬中断留下的 running 回执须先核对 Job，不能
当作终止结果。没有自动恢复优化器/checkpoint；可审查收集的完整路径，作为新 Job 的 images。

最高内部 image 始终标为 validated_ts=false。继续鞍点优化、虚频模式归属和双向 IRC
端点/极小点验证。多峰、中间体、IRC 同势阱可能要求重构假设、分别搜索基元步骤。
结合[故障诊断](../../method-selection/references/search_recovery.zh-CN.md)、
[局部结构诊断](../../material-preparation/references/local_diagnostics.zh-CN.md)和
[轨迹/报告工具](../../report/references/research_tools.zh-CN.md)检查证据。
