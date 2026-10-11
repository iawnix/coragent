> XYZ runner 支持 opt、sp、opt-sp；显式 GJF runner 还接受 none、opt、frequency、minimum、saddle、irc 检查。这些检查不确立振动模式性质或端点身份。

# Gaussian 验证

向 map 添加研究记录前，先核验已收集的主要 Gaussian 输出。

## 程序与 Intent

对照不可变 calculation intent 检查正常终止、route、方法/基组、电荷、多重度、溶剂化/
环境、色散、grid、SCF 处理、优化与频率关键词、约束、资源和重要 warning。当 adapter 能
确定输入错误时，应在远端提交前拒绝。

## 驻点

将正常终止、驻点确认、优化收敛、虚频数量与方法一致性记录为不同研究记录。普通一阶
鞍点必须准确具有一个虚频。频率、位移与可视化分别记录为有来源支持的值；只有将位移与
假设中的成键变化联系后，才能把它作为反应坐标事实。

## 松弛扫描

对于 Gaussian 执行器，核验 route 包含受支持的 `Scan` 或 `ModRedundant` 扫描指令，
不可变 intent 中声明的坐标和点数确实存在，并且解析 profile 包含预期点数、能量和坐标。
完整扫描只是能量曲线，不是过渡态验证；曲线极大值只能作为后续鞍点工作的候选。

## 局限与条件

在研究笔记中明确检查标准、支持证据、未解决问题和下一步，引用实际收集的材料。计算完成不能代替对科学结论的判断。

失败恢复先看所选计算段的主要诊断，再看后续终止信号。`irc_hessian_missing` 需要支持的 Hessian 来源（CalcFC、具有兼容 checkpoint 数据的 ReadCartesianFC 或 FCCards），不能使用 ReadFC。`irc_corrector_limit` 应检查最后有效路径点、步长和校正步数，在有限预算内尝试减小步长或调整校正设置，并分别保留正反向覆盖范围。`coordinate_transform` 应先检查原子对应、过近接触与端点对齐，再选择新种子或合适坐标方法。这些消息之后的 segmentation 信号不单独证明硬件故障。保留失败输入与日志，更改输入使用新尝试身份。部分 IRC 轨迹不能证明端点连通性。
