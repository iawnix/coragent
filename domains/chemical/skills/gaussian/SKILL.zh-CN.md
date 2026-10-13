---
name: gaussian
description: 准备、执行并检查 Gaussian 单点、优化、频率、过渡态、IRC、QST 和显式扫描输入。
---

# Gaussian 计算

XYZ 的 `sp`、`opt`、`opt-sp` 使用 `chemical.gaussian@1`，默认采用
M062X/6-31G**、Opt=Tight 或 SP、SCF=Tight、Int=UltraFine。完整显式
输入使用 `chemical.gaussian-input@1`，两者都采用目标的 `gaussian` 绑定。

收集后可用 `chemical.gaussian-evidence@1` 规范化原始日志 section，供独立的
[驻点、模式与 IRC 检查](../validation/references/general_checks.zh-CN.md)使用。
这些分析 Job 使用 structure，不重跑 Gaussian，也不从正常终止直接认证 TS。

准备参数前先选择输入模式：

| Executor | 准备入口的输入 | `--` 后面的参数 |
| --- | --- | --- |
| `chemical.gaussian@1` | `--input geometry=input.xyz` | `--task opt/sp/opt-sp` 同时决定计算和检查；省略 `--validation`。 |
| `chemical.gaussian-input@1` | `--input input=input.gjf` | `--validation opt/sp/frequency/minimum/saddle/irc/none` 检查 GJF 中的 route；省略 `--task`。 |

两种模式均不接受 `--task-validation`。XYZ 优化时删除这个选项及其值，保留 `--task opt`，不要改成 `--validation opt`。频率、极小值、鞍点或 IRC 检查需要具有相应 route 的显式 GJF。

查看所选 executor 的帮助，在 `chemical.gaussian` 和 `chemical.gaussian-input` 中按模式选择：
`"$CORAGENT_PYTHON" -m research_agent.application.executors --executor chemical.gaussian --version 1 --help`。
需要诊断软件时，对此入口与所选环境执行[定向环境检查](../method-selection/references/runtime_environment.zh-CN.md)。

生成文件前，在命令中显式 cd 到 research_create/research_read 返回的 work_dir，或使用该目录下的绝对输出路径；未关联 Node 时使用工作区内的 research/work/。work_dir 是返回的位置建议，不是 bash 参数。以下相对路径示例假设已在同一命令中切换到工作目录；输入若在其他位置，请使用绝对路径。报告放在 reports/，不要在工作区根目录散落文件或移动历史请求。

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian --version 1 --input geometry=input.xyz --output prepared/gaussian.json -- --task opt-sp --charge 0 --multiplicity 1
```

bash 命令只准备并校验 Job 请求；`prepared/gaussian.json` 是请求文件，不是计算结果，此时尚未启动 Gaussian。参数错误时修正后重新准备。成功后检查请求，将返回的文件路径和摘要连同对应 node_id 交给 `job_start`，计算耗时短也一样（占位符替换为实际返回值）：

```json
{"node_id":"<返回的 node_id>","request_file":"<返回的 request_file>","request_sha256":"<返回的 request_sha256>"}
```

提交准备好的请求时，不要另外添加 command、inputs、outputs 或 platform 覆盖字段。用返回的 job_id 调用 `job_status`，执行结束后用 `job_collect` 保存产物及来源。`research_result` 引用收集到的 Artifact；收集回执用于 evidence_refs/check_refs，不能当作文件 Artifact。

输出和电子态语义见
[共享 runner 契约](../method-selection/references/runner_results.zh-CN.md)。
检查 route 回读、正常终止和收敛。缺少频率证据的优化结构不能确认为极小值。

## 显式 Gaussian 输入

为 TS/Freq/IRC/QST/scan 准备完整 .gjf。每个 Link1 段必须匹配请求的
`--method`、`--basis`、`--threads`、`--memory-mb`、`--charge` 和
`--multiplicity`。Geom=AllCheck 的电子态需要通过 checkpoint 证据核对。
用 `--dependency /absolute/source.chk=previous.chk` 暂存依赖，输入文件中
只引用相对暂存路径，并收集后续计算需要的 checkpoint。

Gaussian 按空行结束输入 section。因此每个显式 `.gjf` 的文件末尾都必须有一个
空行（最后一个坐标或附加 section 后必须有两个换行符），每个 Link1 段之间的
空行边界也必须保留。如果文件只停在最后一个坐标行，Gaussian 可能在计算开始
前就因输入解析失败而退出。提交前先检查这一点；研究 Job 不要绕过 executor，
直接用 shell 调用 Gaussian。

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.gaussian-input --version 1 --input input=ts.gjf --collect results/ts.chk --output prepared/ts.json -- --method M062X --basis '6-31G**' --charge 0 --multiplicity 1 --threads 12 --memory-mb 4000 --validation saddle
```

`--validation opt/sp/frequency/minimum/saddle/irc/none` 仅用于此显式 GJF 模式，选择 runner 检查，不会替 GJF route 添加计算关键词。
`saddle` 检查驻点收敛和一个虚频；还需按实际反应坐标分析模式方向。IRC 输出路径与
端点材料，使用适用分析确认端点身份。注册的 `chemical.gaussian_saddle` 和
`chemical.gaussian_irc_connectivity` 虽然名称通用，实际是 DA 专用检查，不能默认用于其它反应。
显式扫描输入可以执行，当前没有专门验证扫描完整性的内置验证器。

内置解析器区分参考 SCF 与受支持的目标能量，不认证激发态或任意相关方法的能量；
`--validation none` 也不绕过此边界。保留原始输出，对未支持的量使用适用分析，见
[能力范围与能量字段](../method-selection/references/capabilities.zh-CN.md)。

详见 [Gaussian 科学验证](references/gaussian_validation.zh-CN.md)。

- [二维弛豫扭转扫描](references/relaxed_scans.zh-CN.md)

嵌入材料端点的 QST2/QST3 准备与有界 ModRedundant 扫描网格见
[材料路径操作](../candidate-generation/references/path_search.zh-CN.md)。
Gaussian 扫描适配沿用 HF/DFT SCF 能量范围。梯度/NEB 另用 chemical.gradient-gaussian@1、
chemical.neb-gaussian@2，设置见路径操作中的电子态适配说明。

## 明确电子态的计算

chemical.electronic-gaussian@1 提供独立的类型化适配器，支持有限范围的基态自旋
HF/DFT 与闭壳层单重激发 TDDFT/TDHF/TDA 单点/优化。chemical.state-tracking@1
用提供的 AO 跃迁密度及跨几何重叠度量比较特征，识别 root 改变和歧义。
先读[电子态合同](references/electronic_states.zh-CN.md)。原生固定 root 优化在缺少
独立特征信息时保留态连续性未验证。既有 Gaussian 通用能量保护继续有效。
不同自旋交叉使用 [surface-crossing](../surface-crossing/SKILL.zh-CN.md)。

SCF/TS/IRC 故障、checkpoint 复用和 route 不匹配见[搜索诊断与恢复](../method-selection/references/search_recovery.zh-CN.md)。新梯度驱动 NEB 使用独立 path_gaussian 绑定的 [ASE NEB v2](../candidate-generation/references/ase_neb_executor.zh-CN.md)。
