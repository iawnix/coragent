# Gaussian 电子态计算与跃迁特征跟踪

`chemical.electronic-gaussian@1` 使用 input 输入角色、可选 path_gaussian 绑定，
输入 schema 为 chemical-electronic-input/1。必需 material（内嵌有坐标材料，1–128
原子）、task（sp/opt）、settings。本适配器暂不支持显式同位素质量、隐式溶剂、
任意 route 扩展、外部基组文件或多参考方法。

settings 必需 theory（ground/td/tda）、functional（HF、B3LYP、PBE1PBE、
CAM-B3LYP、wB97XD、APFD）、显式 basis。可选 threads（默认 1）、memory_mb
（2000）、timeout_seconds（600，最大 86400）、max_cycles（100，最大 1000）、
spin_tolerance（0.1，最大 0.5）。TD/TDA 还需整数 root、nstates，满足
1 ≤ root ≤ nstates ≤ 32。

ground 要求声明给定多重度表面的基态；单重态使用受限 SCF，其它多重度使用非受限。
TD/TDA 当前只支持闭壳层单重态参考的单重激发，材料 multiplicity=1，并声明
`electronic_state:{kind:"excited",method:"TDDFT",root:1}`；HF+td 用 TDHF，
tda 用 TDA。root 属于局部方法/几何；开壳层 TD、单重参考到三重激发和破缺对称态
不能经此窄接口冒充支持。

生成 TD/TDA(Singlets,NStates,Root)，sp 使用 Force，opt 使用 Cartesian Opt，
配合 NoSymm 和 tight SCF，限定气相。核对 Gaussian 16 版本、route、电荷/参考
多重度、终止、各 SCF/选中态区块、完整 root 列表、Input orientation 与原轴力表。
力取负号并由 Eh/bohr 转为 Eh/Å 的 Cartesian dE/dR；SP 坐标容差 2e-6 Å。
opt 要求四项力/位移数值判据通过，不只检查“已收敛”字样。拒绝覆盖已有输出目录。

激发态能量来自绑定于目标选中态标记的 Total Energy, E(TD-HF/TD-DFT) 或
E(CIS/TDA)，并核对其与参考 SCF+选中激发能相符，容差 1e-4 eV。
参考 SCF 单独保存；旧 Gaussian parser 对未支持目标能量的保护保持有效。
检查非受限 SCF 湮灭前 S² 或选中激发态 S²；受限单重态按行列式确定 S²。
合理 S² 不证明波函数稳定或全局最低 SCF 解。

输出 result.json、原始计算文件、evaluation.json；成功时另有 material.json。
优化后保留原子/态来源，不把原始图直接断言为新几何身份。超时清理进程组，
Gaussian scratch 置于尝试目录并删除；失败保留日志与 failed 结果。
不静默使用检查点延续某个电子分支。

保留每次几何的打印组态/root 谱，但 state_continuity.status 为 not_assessed：
轨道编号与 root 数字不是跨几何态重叠。因此固定 root 优化收敛不自动等于最初指定态
的可靠优化；需检查近简并并补充独立特征分析。特征不明确时应修订计算，不能给通过标签。

`chemical.state-tracking@1` 使用 structure 环境与 input 角色，输入
chemical-state-tracking-input/1，包含 2–32 个 frames、相邻 links、initial_root。
每帧包含 material（几何/原子顺序载体）、source_sha256、basis_definition_sha256、
ao_overlap（正定帧内 AO 度量）、1–32 个 states。每态有 root、energy_hartree、
multiplicity、transition_density（方形 AO 跃迁密度，最大 128 AO）。
每个 link 有 from_source_sha256、to_source_sha256、source_sha256、ao_cross_overlap；
组合帧内/跨帧度量须半正定。

特征分数为
`abs(tr(Da.T Sab Db Sab.T))/sqrt(tr(Da.T Saa Da Saa) tr(Db.T Sbb Db Sbb))`。
不受整体相位影响，对一致的 AO 基变换不变。默认 minimum_overlap=0.8、
minimum_margin=0.1、degeneracy_hartree=1e-4，都是显式筛查阈值，不是普适物理常数。
重叠低、匹配竞争或任一侧同自旋能级近简并时返回 inconclusive 并停止赋值；
最佳匹配 root 改变时返回 root_changed，不能静默当成固定 root 连续。
这是跃迁特征跟踪，不是完整多电子波函数保真度或 diabatic Hamiltonian。

Gaussian 打印的 MO 组态不提供这些 AO 张量及跨几何度量。需从明确的密度/重叠导出
来源获得并绑定 Artifact，不可虚构重叠或用 root 相等替代。本包尚无自动
Gaussian checkpoint→AO 跃迁密度提取，这个证据缺口在每次原生结果中明确显示。

测试使用合成日志、基变换张量和确定性原生命令替身。语法参考
[Gaussian TD 官方说明](https://gaussian.com/td/) 及本机 Gaussian 16 A.03 自带输出，
包括独立的 TDA 总能量标签。尚未进行真实激发态优化精度基准。
