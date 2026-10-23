---
name: crest
description: 使用 CREST 搜索构象和刚性片段排列，并将可追溯的集合成员交给后续反应计算。
---

# CREST 构象与复合物采样

[English version](SKILL.md)

## 脚本路由

按 executor ID 查看[操作入口](references/commands.zh-CN.md)，再读取本 Skill 中对应的输入与验证合同。普通调用不需要阅读源码；`scripts/` 中未列出的文件是内部辅助模块。

当构象、片段取向或弱复合物堆积可能改变反应搜索时使用 CREST。典型场景包括柔性反应物、多个转子构象的催化剂、预反应复合物，以及需要在过渡态搜索前采样相对姿态的刚性片段。

## 输入与输出

从带有显式坐标、电荷、多重度、片段信息和研究溶剂模型的 material 开始。常规搜索用 GFN2；需要便宜宽筛选时用 GFN1。能量窗口要能保留化学上不同的构象，适配器默认 6 kcal/mol。`--max-members` 限制结构化解析数量，默认 256、允许 1–1024；它不限制原生采样，也不决定最终筛选多少成员。

CREST 可以生成单分子构象集合、刚性片段复合物集合、按能量/多样性/记录 ID 选择的子集，以及供反应中心搜索使用的扰动或组装复合物。

## 推荐流程

1. 准备母体 material，并把来源 digest 作为集合父记录。
2. 用 `chemical.crest@1` 设置 GFN 方法、搜索/优化级别、溶剂、线程、超时和能量窗口。
3. 检查运行状态与 `primary.parsing_status`：completed 运行的 limited 解析表示还有未读输出，不是搜索失败。需要完整集合时，明确提高读取预算并重解析已保留文件，不因读取上限重跑 CREST；需要后续复用时，用 `chemical.crest-ensemble@1` 导入原运行或派生重解析回执。
4. 用 `chemical.ensemble-select@1` 按声明规则选成员。若反应扭转角或进攻面不同，应保留多个低能成员。
5. 对分离反应物，用 `chemical.complex-sample@1` 的 `assemble` 或 `perturb` 模式采样，检查接触后交给 `reactive-geometry` 或 `candidate-generation`。
6. 在研究方法下优化或单点评估选中的成员，再用相同方法和电子态比较反应候选。

运行记录保留成员 ID、坐标、母体、溶剂、方法、能量、筛选决定和部分完成状态。后续引用某个构象或复合物姿态时使用这些 ID。

## 已注册操作与脚本

- `chemical.crest@1` -> `skills/chemical/crest/scripts/crest_run.py`；参数包括 `--method gfn1|gfn2`、`--search-level`、`--opt-level`、`--solvent`、`--energy-window`、`--max-members`、`--threads` 和 `--timeout`。
- `chemical.crest-ensemble@1` -> `ensemble.py`，导入 material 与 CREST 运行结果。
- `chemical.ensemble-select@1` -> `ensemble.py`，按规则筛选集合。
- `chemical.complex-sample@1` -> `ensemble.py`，组装或扰动刚性片段。

通过标准 executor 和 Job 生命周期执行。输入 schema 见[后端合同](references/crest_backend_contract.zh-CN.md)，集合选择和复合物记录见[集合合同](references/crest_ensemble.zh-CN.md)。

`scripts/crest_io.py` 提供[重解析命令](references/crest_ensemble.zh-CN.md#重解析已保留输出)，读取既有证据并生成新回执，不调用 CREST，不覆盖源文件。

## 如何交给下一步

追求低能人口时使用最低的几个成员；反应中心存在多个扭转角、进攻面或取向时扩大成员集。集合成员是后续计算的起始几何，频率、过渡态、IRC 和自由能解释由对应操作 Skill 完成。
