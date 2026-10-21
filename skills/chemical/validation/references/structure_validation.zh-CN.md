# 分子结构合同

结构比较需要显式化学 身份 与几何规则。按行顺序比较坐标前先核验原子 mapping。

## Identity 与 Mapping

核验元素计数、电荷、多重度/电子态、相关同位素与一一原子 mapping。Mapping 可以来自
稳定原子顺序、显式 map metadata、图同构或经审查的确定性归属。有歧义的对称等价 mapping
仍是局限。

## 对齐

中心化后，在所选映射原子上使用 Kabsch 最小二乘刚性对齐。应用一次 proper rotation；
除非科学比较明确要求，否则不允许反射。报告对齐 RMSD 和所用原子子集/权重。

刚性对齐后，比较键长、键角、二面角、形成/断裂接触、手性和势阱 身份。

## 科学记录

在研究笔记中明确检查标准、支持证据、未解决问题和下一步，引用实际收集的材料。计算完成不能代替对科学结论的判断。

端点 身份 还要结合全局 RMSD 与渲染结构检查片段排列、构象和立体化学。

## 执行边界

用 `chemical.map-candidates@1 --mode identity` 建立图上的对应关系，
`chemical.conformer-compare@1` 做纯旋转对齐及内坐标比较，`chemical.compare@1`
比较分子身份与指定立体化学。保存来源摘要、选定原子对应和对称性候选。
从 XYZ 比较身份时，同步记录推断的分子图和指定电荷。
操作见[结构分析](../../material-preparation/references/structure_analysis.zh-CN.md)。
