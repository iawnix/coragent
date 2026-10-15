# CREST 后端合同

本参考只记录注册后端边界。`chemical.crest@1` 暂存 chemical-material/1 输入，调用配置的
CREST 3.0.2 绑定，并记录原生输出文件和来源摘要。适配器保留方法、溶剂、电荷、多重度、
成员 ID、坐标和部分运行状态。其它版本和原生选项必须通过显式声明的通用 Job 执行。

`chemical.crest-ensemble@1`、`chemical.ensemble-select@1`、`chemical.complex-sample@1`
通过 structure 绑定消费或转换这些记录。成员筛选和刚性放置语义属于独立操作合同，见[集合操作](crest_ensemble.zh-CN.md)。

后端回执是执行证据，不表示搜索穷尽、极小点认证、反应身份、自由能或过渡态有效性；这些
问题属于操作和 validation Skill。
