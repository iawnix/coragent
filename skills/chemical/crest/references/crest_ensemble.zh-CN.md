# 构象集合执行与筛选

[English](crest_ensemble.md)

## 内容

- [独立 Job](#独立-job)
- [原生封装与证据](#原生封装与证据)
- [重解析已保留输出](#重解析已保留输出)
- [身份、筛选与独立精修](#身份筛选与独立精修)
- [刚性复合物输入](#刚性复合物输入)

## 独立 Job

全部入口版本为 `1`。登记输入 Artifact，使用已安装控制解释器准备请求；
下列占位符应替换成实际绝对路径和 Artifact 引用：

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.crest --version 1 --input material=<material.json> --input-artifact <material-ref> --output <request.json> -- --method gfn2 --threads 2 --timeout 3600 --energy-window 6
```

将返回的 request_file/request_sha256 和 node_id 交给 job_start，终止后收集。
同一准备器可独立调用以下入口：

| 入口 | 输入角色 | 转发参数 |
| --- | --- | --- |
| `chemical.crest` | `material` | `--method gfn1\|gfn2`、`--search-level normal\|quick\|squick\|mquick`、`--opt-level normal\|tight\|vtight`、`--threads`、`--timeout`、`--energy-window`、可选 `--solvent`、`--max-members` |
| `chemical.crest-ensemble` | `material`、`run`（收集的 result.json） | 无 |
| `chemical.ensemble-select` | `ensemble`（chemical-ensemble/1） | `--energy-window 6 --rmsd .1 --max-selected 32 --max-pairs 1024 --max-candidates 64 --max-search 20000` |
| `chemical.complex-sample` | `input`（chemical-complex-input/1） | 必须 `--mode assemble\|perturb`；`--samples 16 --max-attempts 256 --seed 0 --min-separation 3 --max-separation 6 --translation .5 --rotation-degrees 30 --clash-scale 1.2` |

CREST 需要目标机 `crest` 命令与 Python wrapper 绑定；`wrapper.lock` 可为显式配置
的后端提供 Python，不安装原生求解器。激活脚本需暴露相容的原生依赖。
按 runtime `python` 检查环境，再执行有界科学 Job。环境安装不默认运行 CREST
计算冒烟测试；环境和导入通过本身不证明搜索可用。其它三个入口使用 `structure.lock`。

## 原生封装与证据

当前内置封装固定 **CREST 3.0.2** 命令/输出语义，支持 GFN1/GFN2、明确 ground 态、
已知电荷/多重度和普通同位素质量。`--uhf` 为多重度减一，并检查电子奇偶性。
省略溶剂明确表示气相；`--solvent water` 使用 ALPB。不提供原生约束或激发态跟踪。
原生搜索随机性没有被此接口固定。

输入 chemical-material/1，要求按当前原子顺序提供 angstrom 坐标，1–256 原子。
默认 GFN2、normal 搜索、vtight 优化、单线程、3600 秒、6 kcal/mol 窗口、
结构化读取预算 256 成员（可增至 1024）。版本不支持、输出缺失、超时、非零退出或主要
证据不一致时 Job 失败，仍保留 result.json 和可收集的原始文件。封装退出时终止子进程组。

主要文件为 crest.out、crest_conformers.xyz、crest_best.xyz、crest.energies，
每个最多 64 MiB。XYZ 注释是绝对 hartree；crest.energies 是从 1 连续编号的
相对 kcal/mol。核对行数、元素顺序和能量差（容差 0.002 kcal/mol）；best 必须
在完整读取时以固定顺序匹配最低能成员（1e-6 Å、1e-7 hartree）。已观察到损坏尾部时，
保留有效帧前缀并将解析标为 invalid；不跳过坏行，不把缺失能量补零。

`--max-members` 限制结构化成员和能量行的读取，不控制 CREST 采样或最终筛选数量。
`primary.parsing_status` 为 complete、limited 或 invalid。仅达到读取上限时，原生运行
仍是 `status=completed`，封装退出码为 0，但 `primary.complete=false`。`read_budget`
记录本次最大值、members_read、energy_rows_read，以及 has_unread_members /
has_unread_energy_rows。未读尾部尚未验证，不推测总成员数。best 几何不在前缀内时，
best_membership_verified=false，需更完整读取后再验证成员归属。已经发现的缺失、损坏
或不一致仍会失败，即使同时触及读取预算。4 个完整原文件及全文摘要始终保留；
部分导入的集合仍是 complete=false。

例如原生输出 138 个构象但设置 `--max-members 64`，会得到 64 个已解析成员及明确的
未读尾部，需要更多覆盖时重解析已有文件，不重新搜索。限制后续精修数量用
`--max-selected`；max-pairs、max-candidates 和 max-search 限制比较工作。
`--max-candidates 64` 是每次比较的图映射上限，不是来源集合的构象数量上限。

上游依据：[命令参数](https://github.com/crest-lab/crest/blob/v3.0.2/src/confparse.f90)、
[能量表输出](https://github.com/crest-lab/crest/blob/v3.0.2/src/cregen.f90)。

## 重解析已保留输出

用控制解释器执行已安装 Skill 的 `scripts/crest_io.py`。该命令不调用原生求解器，
不新增 executor。提供原 material、原运行回执和包含 4 个未改变主要文件的目录；
输出的父目录应已存在：

```text
"$CORAGENT_PYTHON" <installed-crest-skill>/scripts/crest_io.py --directory <collected-primary-directory> --material <original-material.json> --run <original-result.json> --max-members 256 --output <new-work-directory>/crest-reparsed.json
```

命令核对 material 摘要与原回执、4 个主要文件摘要与原回执一致，再调用同一个有界解析器。
已有输出文件会被拒绝。新的 chemical-crest-run/1 回执保留原生命令、设置和退出码，
只更新解析及由此得出的封装状态，用 reparse_of 保存原回执摘要和主要文件摘要。
原生非零退出不会因重解析而变成成功；历史 Job 状态与已收集 Artifact 不变。

把新回执作为带源引用的派生材料登记，即可作为 chemical.crest-ensemble@1 的 run 输入。
声称完整覆盖前检查新的 primary.parsing_status。提高读取预算是 1–1024 范围内的
明确选择，不自动扩限，也不静默裁剪。

## 身份、筛选与独立精修

导入将精确材料文件摘要绑定到自包含运行回执；原始文件摘要保留于 derivation，
同时保留 Job Artifact 来源。成员继承本地 ID、同位素/图对应、态及来源结构。
RDKit 在固定顺序下推断坐标键、局部形式电荷/自由基及指定立体化学，范围为
H/B/C/N/O/F/Si/P/S/Cl/Br/I。缺图/电荷或成键求解不确定时为 not_assessed；
不为范围外金属猜测身份。这些推断不是电子态或原子轨迹证明。

筛选使用全原子 RMSD、纯旋转和有界图对称映射；复合物只作一次整体对齐。
只合并身份/态声明相容的几何重复项；不完整比较保留候选或明确延后。
每个成员记录 selected/duplicate/deferred/outside_energy_window/excluded/unusable；
比较预算耗尽与数量上限分别报告。能量排序要求与参考物种一致，且电子能模型
（方法、溶剂、约束等）相同；混合模型关闭能量排序，但仍可选几何代表，不能称为
最低能代表。缺失能量/身份的候选保持未排名。不推断自由能、布居或全局最低点。
必须保留来源集合。

导入/采样/筛选输出 result.json、refinement.json 和
members/NNNN/{material.json,geometry.xyz}。XYZ 可独立交给相容的 xTB/Gaussian/CF22D
单点或优化 Job，显式保持态与溶剂。现有 xTB 快捷封装不能表达溶剂；溶液精修应选
适用的经核实命令，不能静默切成气相。这些集合操作本身不提交优化。普通 XYZ 不编码同位素质量、电荷或电子态；
精修必须参考完整材料，显式同位素成员应使用能表达相应质量的求解器输入。

## 刚性复合物输入

chemical-complex-input/1 包含 `materials: [<嵌入 chemical-material/1>, ...]`。
每个来源需坐标和图推导或显式声明的片段。单材料保持原态/ID；多材料拼接为
part1_atom1 等 ID，并记录 atom_lineage。电荷仅在全部已知时求和；总
`multiplicity`、`electronic_state` 显式提供或保留未知，不相加多重度。
重复图 atom-map 标签需要显式解决。最多 16 来源、2–16 片段、256 原子。
第一个片段始终固定；可用 `fixed_fragments: [0,2]` 固定其它零基序号片段，至少一个可动。

可选 `distance_constraints: [{"atoms":["part1_atom1","part2_atom1"],"minimum":3,"maximum":5}]`
使用合并后 ID 和 angstrom。assemble 抽样纯旋转及相对第零片段的质心距离；
perturb 在碰撞/约束允许时保留原构型，再有界扰动质心位置和转角。记录 PCG64 种子、
变换、拒绝数与有限尝试预算。片段间距离小于 clash_scale 倍共价半径和时拒绝。
这些是刚性候选排布，不是结合能或优化后复合物；约束不自动用于后续优化，
片段内部构象需要另行搜索。
