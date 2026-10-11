# 基于材料的 QST、扫描与 NEB

[English](path_search.md)

## 内容

- [独立执行与环境](#独立执行与环境)
- [QST2 与 QST3](#qst2-与-qst3)
- [一维与二维弛豫网格](#一维与二维弛豫网格)
- [梯度 calculator 与 NEB](#梯度-calculator-与-neb)
- [证据与限制](#证据与限制)

## 独立执行与环境

以下五个入口均为版本 `1`，输入角色只有一个 `input` JSON Artifact。
不要求反应名称、DA 拓扑或完整研究流程。通过既有准备器生成请求，
将 request_file/request_sha256 和 node_id 交给 job_start，终止后收集。
占位符应换成真实绝对路径和 Artifact 引用：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.scan-xtb --version 1 --input input=<work_dir>/scan.json --input-artifact <scan-ref> --output <work_dir>/scan-request.json -- --max-points 16
```

| 入口 | 后端绑定 | 结果 |
| --- | --- | --- |
| `chemical.qst-prepare` | `structure` | QST2/QST3 ts.gjf、对应和设置清单 |
| `chemical.scan-xtb` | `path_xtb` | 逐点受限优化、无约束能量、实际坐标与失败记录 |
| `chemical.scan-gaussian` | `path_gaussian` | 逐点 ModRedundant 优化、已区分类型的能量和收敛证据 |
| `chemical.gradient-xtb` | `path_xtb` | 绑定结构的 Cartesian 电子能与梯度 |
| `chemical.neb-xtb` | `path_xtb` | 完整路径、逐 image 能量/梯度、NEB 力历史和候选 |

原生路径操作需要 **RDKit/NumPy 加已配置的求解器**，不同于只需标准库的旧 Gaussian/xTB
包装器。为 path_xtb/path_gaussian 配置相应原生命令/激活脚本，再以
`--job-profile local:path` 为显式配置的后端绑定已有 structure.lock。
此 profile 不安装求解器、不默认执行原生科学验收；先按 --executor/--version
检查选定入口环境，再运行有界科学案例。旧 wrapper 环境不变；不新增 ASE，
也不根据 PATH 自动猜测原生绑定。

嵌入材料为 chemical-material/1，要求已有 angstrom 坐标、2–256 原子、已知电荷/多重度
和明确 ground 态。显式同位素质量、激发态/跨态需其它经核实输入。
保留来源材料，不预先偷偷优化、不独立对齐片段，也不从名称猜测坐标。

## QST2 与 QST3

`chemical-qst-input/1` 包含 `reactant`、`product`、`mapping`、`settings`。
材料是嵌入对象，mapping 是本地 ID 的完整双射，例如
`[["atom_1","product_atom_4"], ...]`，包括所有显式 H。核对元素和态声明，
把产物重排成反应物顺序，并记录置换。QST3 额外提供 `guess` 和独立的
`guess_mapping`（反应物 ID 到猜测结构 ID）；中间猜测不要求有已认证的极小点图。

Gaussian settings 必须提供 method、basis、threads、memory_mb、timeout_seconds、
solvent、solvent_model（gas+null，或 SMD+溶剂名）。可选 max_cycles 默认 200，范围
1–2000。不注入额外 route/基组文本；Gen/GenECP/ChkBasis 仍需通用显式输入。
例如 `{"method":"HF","basis":"STO-3G","threads":1,"memory_mb":512,"timeout_seconds":600,"solvent_model":"gas","solvent":null}`。

输出 Opt=(QST2 或 QST3,CalcFC,MaxCycles=...) Freq、SCF=Tight、Int=UltraFine、NoSymm。
将 ts.gjf 独立交给 chemical.gaussian-input，保持相同方法/基组/态/资源。
准备成功不证明端点为极小点或属于同一基元步骤；跨多步端点可能需要反应网络。

## 一维与二维弛豫网格

`chemical-scan-input/1` 包含 `material`、`settings` 和一或两个 `axes`：

```json
{"kind":"distance","atoms":["atom_1","atom_2"],"values":[1.5,1.8,2.1],"unit":"angstrom","tolerance":0.03}
```

angle 使用 3 个 ID、degree，值严格位于 0–180；dihedral 使用 4 个 ID，值位于
-180–180，误差按周期比较。每轴须有不同的已存在原子 ID、显式有限数值和正容差。
笛卡尔积最多 256 点，第二轴变化最快。每点都从**原始几何**独立开始，不沿用前一点
优化结果；避免失败邻点形成隐藏依赖，但不代表追踪同一个构象分支，约束可能导向不同势阱。

xTB settings 必须包含 method（gfn1/gfn2）、threads、timeout_seconds、solvent_model
（gas/ALPB）和 solvent（null/名字）。可选 opt_level 为 normal/tight/verytight，默认 tight；
force_constant 默认 1，采用原生 xcontrol 约定。封装固定 accuracy=1、电子温度 300 K。
Gaussian 使用前述设置和原生 ModRedundant 冻结内坐标。

xTB 使用附加约束势，并非精确冻结。优化后在同一几何上额外运行**无约束**能量/梯度，
作为物理电子能；含约束的原始优化能单独保留。独立核对实际坐标和目标偏差。
正常退出、打印收敛标志或能量行数相符，本身不能使扫描点成功。

`--max-points` 限制本次新尝试数（1–256）。result.json 保留全部 pending/succeeded/failed
点及目标、实际值、几何、能量、证据和摘要。预算停止为 partial，退出非零，仍应收集材料。
新 Job 可在原 spec 中以 `previous` 嵌入终止且已收集的结果：核对计划/逐点摘要，
复用成功点、执行待运行点；失败点默认保留，只有显式 `retry_failed: true` 才重试。
复用点的原始文件摘要路径指向上一结果的收集 Artifact。running/unknown 回执不可重放，
先核对 Job 状态与收集证据；硬终止可能只留下 running 回执，不能编造完成状态。

candidate.xyz 和 candidate.material.json 是成功采样点中的最高能结构，不保证位于网格
内部、不保证为鞍点，也不能直接当作反应能垒。

## 梯度 calculator 与 NEB

`chemical-gradient-input/1` 包含 `material`、xTB `settings`。适配器固定 xTB 6.7.1
GFN1/GFN2 CLI 语义，读取完整单周期 Turbomole gradient 文件。其中坐标为 bohr、
能量为 hartree、梯度为 hartree/bohr。核对元素顺序、坐标、与日志一致的能量、版本、
SCC 和终止状态。日志打印态信息时核对一致性；输入声明不证明波函数身份。

chemical-calculation/1 绑定 atom_ids、坐标及摘要、model、收敛和原始来源。
要求电子能和 Cartesian **dE/dR**；仅有能量不能运行 NEB。引擎用
1 bohr = 0.529177210903 Å，显式转换成负梯度力（hartree/angstrom）。
核心算法可接独立 calculator；内置原生梯度适配目前只有 xTB。
Gaussian 梯度/calculator 尚未实现，不能因支持 Gaussian 扫描而声称可运行 Gaussian NEB。

`chemical-neb-input/1` 包含 reactant、product、mapping、xTB settings，可选参数：
image_count 默认 7（3–32）、max_steps 默认 100（0–1000）、fmax 默认 0.001 hartree/angstrom、
spring 默认 0.05 hartree/angstrom²、step_size 默认 1 angstrom²/hartree、
max_displacement 默认 0.05 Å、climb_after 默认 null（禁用爬山，否则指定零基迭代号）。
端点固定并保留，不因此认证其为极小点。

可选 `images` 为 image_count × atom_count × 3 的 angstrom 数组，按反应物原子顺序，
首尾必须与映射端点一致。否则使用不作对齐的线性 Cartesian 插值。
近重合原子和相邻重复初始 image 会被拒绝，应修订路径，不能假定插值在化学上合理。

引擎使用能量加权改进切向、垂直物理力、平行弹簧力，并可将最高内部 image 设为爬山点。
优化器为限制最大位移的投影力松弛，不是 ASE/FIRE/BFGS。收敛量是内部 image 的最大
逐原子 NEB 力范数；要求爬山时必须启动爬山后才可收敛。NEB 力小不证明物理驻点。
最多 2+(max_steps+1)*(image_count-2) 次 calculator 调用，端点只算一次；
原生逐调用超时和外层 Job walltime 都需要纳入预算。

## 证据与限制

候选保持本地原子 ID，来源图/片段/map 标签保存在 derivation；路径可能改变成键，
候选自身的图和片段身份保持未指定。依赖身份的后续使用应单独判定连接关系。

递归收集原始输入/日志、计算证据、路径/网格和 result.json。完成或超时后清理原生
子进程组。NEB 步数用尽或 calculator 失败时保留部分计算及最后一轮完整已求值路径；
候选取自完整已求值的内部 image，不能引用下一轮尚未求值的坐标。
NEB 不自动续跑未知 Job；审查后的旧路径可作为新任务的显式初始 images。

确定性替身测试不证明真实求解器互操作性或搜索精度。称为 TS 前仍需独立身份、端点准备、
模式和 IRC 证据。多峰/多势阱、竞争路径、自由能、态连续性需要相应后续工作。
旧 Gaussian 原始 SCF 序列的扫描回退不等于完整弛豫网格；这些入口逐点保存证据。

## Gaussian 基态自旋梯度与 NEB

chemical.gradient-gaussian@1 和 chemical.neb-gaussian@1 复用已有
chemical-gradient-input/1、chemical-neb-input/1 的几何/映射/预算合同，但 settings
使用[电子态适配器设置](../../gaussian/references/electronic_states.zh-CN.md)，要求
理论 ground 及受支持的气相泛函/基组，绑定 path_gaussian。原坐标轴的力取负并转为
Eh/Å 的 dE/dR，计算证据记录 2e-6 Å 打印坐标精度。独立有限差分与确定性原生 Job
测试核对单位/符号/派发，不代表真实 Gaussian NEB 基准。NEB 算法及未验证候选语义
保持一致，多重度/S² 不证明波函数分支连续。
