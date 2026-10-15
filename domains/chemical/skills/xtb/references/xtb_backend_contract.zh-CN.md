# xTB 后端合同

`chemical.xtb@1` 将 chemical-material/1 字段转换到配置的 GFN2-xTB 绑定，支持 `sp`、`opt`、
`opt-sp`。它记录原生命令、电荷、自旋、溶剂/态字段、输出摘要和解析状态。解析器只接受
文档列出的产物形式；不支持的原生任务输出保留为原始记录，不归类为科学结论。

路径适配器 `chemical.scan-xtb@1`、`chemical.gradient-xtb@1`、`chemical.neb-xtb@2` 使用
`candidate-generation` 下可选的 `path_xtb` 绑定，并由操作层负责约束、梯度和 NEB 证据合同。
本后端合同不选择操作，也不解释科学结果。原生命令示例见[xTB 操作配方](../../method-selection/references/xtb_operation_recipes.zh-CN.md)。
