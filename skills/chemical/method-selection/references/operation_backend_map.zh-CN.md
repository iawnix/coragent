# 科学操作与后端映射

本表把科学操作与执行它的方法/后端分开。`execution.json` 的 `skill` 字段表示执行器的
主要归属，`backend` 表示实现绑定。后端执行成功本身不等于最后一列所列的科学结论成立。

| 科学操作 | 主要 Skill | 方法或后端 | 执行器 | 独立证据或验证器 |
| --- | --- | --- | --- | --- |
| 材料导入、结构检查与反应映射 | `material-preparation` | structure | `chemical.material`、`chemical.resolve`、`chemical.inspect`、`chemical.reaction`、`chemical.map-candidates` | 结构身份、映射和显式键变化检查 |
| 构象/复合物准备 | `material-preparation` 与 `crest` | structure、CREST | `chemical.seed`、`chemical.crest`、`chemical.crest-ensemble`、`chemical.complex-sample` | 集合身份、来源几何和筛选证据 |
| 反应取向构造 | `reactive-geometry` | structure | `chemical.reactive-sites`、`chemical.reactive-pose`、`chemical.reactive-geometry` | 几何安全和显式反应中心观察 |
| 过渡态/路径候选生成 | `candidate-generation` | Gaussian、xTB、ASE | `chemical.qst-prepare`、`chemical.scan-*`、`chemical.path-candidates`、`chemical.gradient-*`、`chemical.neb-*` | 候选来源记录；不作鞍点结论 |
| 过渡态鞍点证据 | `validation` | Gaussian 证据解析器或规范化证据 | `chemical.gaussian-evidence`、`chemical.stationary-check`、`chemical.mode-check` | 驻点、模式方向、电子态和几何检查 |
| TS IRC 连通性验证和势阱归属 | `validation` | Gaussian 或通用 Job | `chemical.path-irc`、`chemical.irc-check` | 双向路径完整性和端点势阱身份 |
| 能量与热化学 | `energetics` | structure 加声明的方法结果 | `chemical.thermochemistry`、`chemical.energy-profile`、`chemical.ensemble-free-energy`、`chemical.scan-slice` | 单位、电子态、化学计量和条件兼容性 |
| 不同自旋表面交叉 | `surface-crossing` | Gaussian | `chemical.mecp-gaussian`、`chemical.crossing-check` | 能隙、投影梯度、态身份和可选曲率 |
| Gaussian 计算后端 | `gaussian` | Gaussian 绑定 | `chemical.gaussian`、`chemical.gaussian-input`、`chemical.electronic-gaussian`、`chemical.state-tracking` | 原始输出和操作层证据 |
| xTB 计算后端 | `xtb` | xTB 绑定或原生命令 | `chemical.xtb`、`chemical.scan-xtb`、`chemical.gradient-xtb`、`chemical.neb-xtb` | 原始输出和操作层证据 |
| CF22D 计算后端 | `cf22d` | PySCF 绑定 | `chemical.cf22d` | 收敛、频率和热化学范围 |
| CREST 计算后端 | `crest` | CREST 绑定 | `chemical.crest` 及集合执行器 | 集合回执和逐成员证据 |

`method-selection` 负责协调这些层并选择命名环境，不替代操作 Skill，也不会把 Job 成功
自动变成科学结论。`geometry-preflight` 是跨任务的前置控制，在坐标进入电子结构计算前使用。



See the [完整运行时注册表](operation_backend_registry.zh-CN.md) for exact executor and validator paths.
