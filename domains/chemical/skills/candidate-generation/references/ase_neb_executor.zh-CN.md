# NEB 可用性

当前提供 `chemical.neb-xtb@1`：有界 NumPy NEB 引擎及 xTB 6.7.1 能量/梯度适配器。
设置、可选 path 环境、收敛与部分结果见[路径合同](path_search.zh-CN.md)。
这不是 ASE 实现；旧 `ase.neb@1` 接口仍不可调用。
安装了 ASE 或找到 xTB/Gaussian，本身不代表已有可执行的 NEB 路径。

若所选环境提供有文档的 NEB 脚本，先核实其真实输入输出合同、calculator 绑定和依赖，
再通过 `job_start` 执行。否则实现并验证有界 runner，或选择保持科学目标的可用候选生成方法。
Skill 本地缺脚本不能证明共享 runner 或外部工具不存在；检查这些入口后再记录具体阻塞。

NEB 需要原子映射明确、顺序一致、电荷和电子态兼容的端点。显式记录端点松弛、插值、
image 数量、优化器、力阈值、calculator 设置和爬山图像策略，保存路径、各 image 能量和
收敛证据。最高能量 image 是候选结构，不是已验证过渡态。

现有执行入口见 [Gaussian Skill](../../gaussian/SKILL.zh-CN.md) 的显式 TS/扫描/QST 输入，
以及 [chemical-input](../../chemical-input/SKILL.zh-CN.md) 的分子种子准备。不同反应假设的执行与任务脚本说明见[候选生成](candidate_generation.zh-CN.md)。
