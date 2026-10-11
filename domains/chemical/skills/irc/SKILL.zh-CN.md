---
name: irc
description: 规划和评估双向内禀反应坐标计算，并将端点归属到已声明的分子势阱。
---

# CoRAgent IRC

[English version](SKILL.md)

使用本 Skill 处理正向/反向 IRC 的设计、运行结果解释、路径完成性、端点提取与端点身份。
Gaussian Skill 负责检查 Gaussian 文件，本 Skill 负责路径的化学含义。

`chemical.irc-check@1` 对规范化证据执行有界来源、路径、极小点与参考构象检查；
`chemical.gaussian-evidence@1 --kind irc` 提取 Gaussian 路径，保留势阱证据未确定。
合同与独立调用见[通用检查](../validation/references/general_checks.zh-CN.md)。

Gaussian 计算从鞍点几何或检查点准备正反向 IRC 输入，保留方法、基组、电荷和电子态，
按实际 Hessian 来源选择输入选项，再通过 `chemical.gaussian-input` 或通用 Job 执行。
[映射路径准备器](../candidate-generation/references/path_preparation.zh-CN.md)也接受通用显式变换，
用 CalcFC 在检查点几何上计算 Hessian；也可以直接准备 Gaussian 输入。可选 DA 几何策略和
注册的 `chemical.gaussian_irc_connectivity` 验证器是专用能力，不是其它反应的前提；应使用
适用方法分析其端点。

从已验证的鞍点候选出发并保留路径方向。核对 IRC 起点与该结构是否一致，分别检查两个
方向的终止与路径完整性、末端几何和梯度，并判断盆地归属前是否需要优化端点。使用明确
的目标 Artifact，通过原子映射、关键内坐标、立体化学和确定性结构比较核验每个端点。

按方向分别记录路径和端点事实。缺失或矛盾的端点证据属于研究记录，但不会隐式
改变研究 Node 或假设状态。详见
[irc_validation.zh-CN.md](references/irc_validation.zh-CN.md)。
