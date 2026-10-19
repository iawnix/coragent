# 分子准备

[English](molecular_preparation.md)

用 `material-preparation` 先准备分子图与原子对应，再生成反应几何。
具体见其[映射准备步骤](../../material-preparation/references/reaction_mapping.zh-CN.md)。

1. 用 `chemical.resolve@1` 解析名称，`chemical.material@1` 导入 SMILES，
   `chemical.inspect@1` 检查图、分子式、电荷和立体化学。
2. 为全部反应物片段建立包含每个显式 H 的持久标签。对每个基元步骤假设，用
   `chemical.map-candidates@1` 辅助选择图上的对应关系，再用 `chemical.reaction@1`
   核验给定映射和声明的变化。产物未知时先保留反应物身份，后续假设沿用这些身份。
3. 将选定的映射 SMILES 交给 `chemical.seed@1`，逐个生成物种。逐行原子表与 XYZ
   一起保存，并贯穿构象搜索、优化和片段组装。已有坐标则连同它与分子图的对应一起保留。
4. 分别探索未指定的立体异构体、构象和接近姿态。二烯 s-cis/s-trans 调整保留其分子图
   和原子标签。路径两端按相同映射顺序组装，记录任何行序变换。

通过 generic executor 准备这些已注册操作，用 `job_start` 提交，将收集的 Artifact
纳入基元步骤记录。把选定映射和反应原子对传给几何构建，模式解释及 IRC 端点比较
继续沿用相同标签。
