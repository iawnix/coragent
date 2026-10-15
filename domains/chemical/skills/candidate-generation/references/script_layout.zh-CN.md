# candidate-generation 脚本布局

脚本按操作和执行角色分组：

- `scripts/path/` 准备映射端点、QST 输入和候选生成所需的路径合同。IRC 输入准备由
  `validation/scripts/irc_preparation.py` 独立负责，不导入候选生成路径代码。
- `scripts/search/` 编排 QST、受限扫描和梯度证据。
- `scripts/backends/` 将 Gaussian 与 xTB 适配到共享路径合同，不定义科学操作的范围。
- `scripts/neb/` 负责 ASE/NEB 计算循环及 CLI。
- `scripts/da/` 只保留局部的旧 Diels–Alder 几何 helper，是兼容策略，不是通用反应限制。

根目录文件仍是现有 Job 和测试使用的兼容入口；它们加载分类后的实现，因此目录
整理不会删除可执行脚本。新的 executor 应使用分类后的入口，并在 staging 闭包中
声明相应的分类模块路径。
