# 领域科学回归

本组回归覆盖研究执行中会改变科学判断的边界：几何与立体化学、Gaussian 证据选择、失败后修正的结果归属，以及实际软件可用性。样例来自公开源码中的固定分子、人工构造日志和本地确定性程序，不使用私有研究材料，也不请求远程模型或计算平台。

## 几何、对称性与原子对应

入口：`tests/unit/test_chemical_geometry_regressions.py`。

| 固定样例 | 判断要求 |
| --- | --- |
| 有标记的非共面四面体 | 整体平移、旋转后的 RMSD 为零；镜像不能被旋转拟合成同一结构 |
| 已指定手性的支链烷烃 | 旋转保留手性，反射必须识别为不同立体异构体 |
| 顺式、反式 2-丁烯 | 相同连接图不能掩盖已指定的 E/Z 差异 |
| 乙醇与等价氢交换 | 原子重排和等价原子置换不改变分子身份；带映射的几何仍遵守其对应关系 |
| 丁二烯与丙烯的声明反应图 | 区分同一产物的等价编号、错误的原子轨迹、真正不同的连接异构体 |
| 非有限坐标 | 作为无法解释的输入处理，不能生成支持或否定机理的结论 |

修复了整数坐标居中计算失败、端点检查遗漏双键立体化学的问题。反应检查现在同时报告产物连接图是否等价与声明映射是否成立；连接图等价不会自动通过严格原子对应检查。原有身份检查不自动重映射；有界映射候选、构象比较与张量重排由下面列出的独立模块覆盖。

## Gaussian 的最终证据

入口：`tests/unit/test_gaussian_scientific_regressions.py`；连同既有 `test_gaussian_explicit_input.py`、`test_chemical_path_execution.py` 验证。

| 故障或边界 | 判断要求 |
| --- | --- |
| 失败进程日志后追加修正成功的运行 | 默认选最后运行；旧错误保留在原段，可显式读取，不污染修正后的结果 |
| 较早驻点成功，后续收敛表不完整、失败或截断 | 不继承旧驻点或拼接两轮收敛表 |
| 较早频率表通过，最终谐振段为空 | 最终频率证据为空；不使用旧表代替 |
| 不同 orientation 类型先后出现 | 最终几何按实际记录顺序选择 |
| 频率使用 Fortran D/d 指数 | 正确读取数值和符号 |
| NaN、无穷、字符串、布尔值或异常终止 | 频率验证为 inconclusive，不能通过“恰好一个负值”的检查 |
| 零、一、多个有限负频率 | 按频率验证器的既有狭窄范围判断；不宣称完成 IRC 或模式归属验证 |

实际运行 Gaussian CLI 适配器的测试使用本地假可执行程序生成合成日志，分别断言程序返回码、解析状态、检查结果和 `scientific_validation`。程序正常退出且日志可解析，并不保证最终证据满足条件。

合成鞍点/IRC 日志只证明解析与判据实现的行为，不是通过量子化学计算获得的过渡态、势垒或连接路径。既有路径回归继续覆盖不相干负频模式、错误起点、错误端点、路径不完整、方法/资源不匹配等情况。

## 失败尝试与修正结果

入口：`tests/integration/test_repaired_job_evidence.py`。

- 实际执行两个本地 Job：原输入失败，修正输入成功。两次输入指纹、Job 和材料回执保持独立；相同修正输入的重复提交指向成功尝试。
- 迟到的原失败诊断不会覆盖修正 Job 的执行事实，也不会更换 Node 的当前评估。
- 成功退出不自动选定科学结论。研究结果必须显式引用材料并选择评估；过期草稿不能覆盖新的评估。
- 同一 Job 出现矛盾终态时保留已确认事实并提示 reconcile，不用另一条观察直接改写历史。
- 相同时间戳、逆序随机 ID 下，近期结果、Node 详情和 Markdown 仍按不可变发布记录排序；重建后顺序一致。

本次修复了按 UUID 排序取“最近结果”导致修正后新结果遗漏的问题。排序不引入第二份可变时间线，也不自动替用户或 Agent 选择结论。

## 计算能力与环境证据

入口：`tests/unit/test_computation_capabilities.py`，沿用既有 executor、environment check 和 Job 接口。

声明有某个 executor、机器可连接、程序文件存在、依赖可导入和科学计算成功是不同事实。回归通过真实本地子进程验证：

- 未配置后端、未知 executor、缺失程序或激活文件分别报告可操作错误。
- 缺失依赖与模块初始化异常分开；不把探测失败解释为该软件原则上不支持某项科学方法。
- 正确配置的本地假程序能够通过准备并成为受管 Job。
- 配置或可执行文件内容变化、文件删除后，旧环境证据不能继续授权原准备请求。
- 平台状态和软件可用性独立；只读目录的 `not_checked` 不被误读为可用或不可用。

没有新增能力注册表、协议别名或探测失败后的自动替代后端。

## 通用化学模块回归

A–J 新增模块的执行合同见[能力清单](../domains/chemical/skills/method-selection/references/capabilities.zh-CN.md)，
实施范围与当时的测试计数见[实施记录](GENERAL_CHEMISTRY_CAPABILITY_PLAN.zh-CN.md)。

| 测试入口（位于 `tests/unit/`） | 主要覆盖 |
| --- | --- |
| `test_chemical_materials.py` | 原文/坐标保真、原子身份、显式 H/同位素、未知声明与材料 Job |
| `test_structure_analysis.py` | 有界映射、对称与镜像、复合物对齐、张量往返 |
| `test_general_evidence_checks.py` | 驻点自由度、模式响应、IRC 端点、缺证据与来源绑定 |
| `test_crest_ensembles.py` | 构象输出一致性、聚类/筛选、复合物采样、超时清理 |
| `test_path_search.py` | QST2/3、扫描续算、梯度有限差分、解析势 NEB、失败材料 |
| `test_energetics.py` | 标准态、热校正、组合能量、低频近似、集合自由能与剖面 |
| `test_kinetics_pathways.py` | Eyring 公式、共同前体分支、解析动力学解、守恒、多步路径与缺口 |
| `test_electronic_crossing.py` | ground/TD/TDA 解析、态特征重叠、Gaussian 梯度/NEB、交叉驻点/曲率与预算 |

这些测试包含真实本地 Job 准备、执行与收集，但原生求解器使用确定性替身。
Worker 的等待、恢复与持续推进另由 `tests/node/native/worker-research-flow.test.mjs`
和 `worker-task-continuation.test.mjs` 覆盖，模型为本地确定性提供方。

## 运行与范围

所有测试使用统一入口，环境、缓存、临时文件与证据留在 `local_debug/`，运行结束必须清理服务：

```bash
python3 -B tools/test/runner.py check --files \
  tests/unit/test_chemical_geometry_regressions.py \
  tests/unit/test_gaussian_scientific_regressions.py \
  tests/unit/test_computation_capabilities.py \
  tests/unit/test_chemical_path_execution.py \
  tests/integration/test_repaired_job_evidence.py
```

领域脚本有内容摘要；修改后先运行 `python3 -B scripts/update_resources.py`。完整回归使用 `python3 -B tools/test/runner.py verify`，wheel 安装环境使用 `source` 套件。

这组测试验证软件实现的判据、数值算法和证据流，不替代真实 Gaussian/集群计算、方法精度校准或真实模型自主研究验收。CoRHub 客户端互操作由独立 `phone` 套件覆盖，范围见[测试运行器](../tools/test/README.md)。
