---
name: crest
description: 适配已声明的 CREST 构象和刚性片段集合 Job，保留成员身份、记录和来源。
---

# CREST 后端

本 Skill 负责 CREST 可执行程序绑定、版本化输入暂存、集合回执解析和逐成员来源。它不选择
反应机理、不排序研究假设、不认证极小点或过渡态，也不把集合能量解释为自由能；这些决策
属于 `chemical-input`、`candidate-generation`、`energetics` 或 `method-selection`。

已注册的适配器：

- `chemical.crest@1` 为配置的 CREST 3.0.2 GFN1/GFN2 绑定暂存明确声明的 ground 态材料。
- `chemical.crest-ensemble@1` 导入回执和精确来源材料。
- `chemical.ensemble-select@1`、`chemical.complex-sample@1` 使用 structure 绑定对 CREST 数据执行确定性记录操作。

适配器保留来源材料、成员 ID、坐标、方法/溶剂元数据、能量字段、筛选决定和部分结果状态；
未知身份或电子态保持为明确记录字段。其它 CREST 版本和原生选项必须通过声明输入/输出的
通用 Job 执行；注册适配器不宣称兼容这些功能。

通过标准 Job 生命周期准备、提交和收集。后端 schema 与暂存边界见[后端合同](references/crest_backend_contract.zh-CN.md)；集合操作见[集合合同](references/crest_ensemble.zh-CN.md)。
