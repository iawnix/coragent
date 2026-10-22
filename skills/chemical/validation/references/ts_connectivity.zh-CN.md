# 绑定 TS 的双向位移与短 IRC

使用 `chemical.ts-connectivity-inputs@1`，输入 `material`（**已优化的鞍点**，固定原子顺序）、`log`（对应 Gaussian Opt+Freq 输出）、`coordinates`（`chemical-mode-coordinates/1`，见通用检查）。生成器重新检查驻点、几何绑定及虚频是否对应目标反应坐标；初始猜测、解析冲突和不支持的电子势能面不能生成通过验证的来源包。

默认生成四份 `Opt=(Tight,MaxCycles=100) Freq` 输入：沿虚频向量分别 ±0.05、±0.10 Å，幅度定义为**单个原子的最大位移**；另生成从原始已优化 TS 出发的正反向 `IRC=(...,CalcFC,MaxPoints=20,StepSize=5)`。可设置 `--amplitudes`、`--max-points`、`--step-size`、`--threads`、`--memory-mb`。StepSize 必须为非零整数，正负号遵循 Gaussian 的单位约定；0.5 无效。生成输入不会自动提交计算。

通过 `chemical.gaussian-input@1` 的显式输入模式运行所需 GJF，并指定一致的方法、基组、电荷、自旋和资源。使用 `--dependency /absolute/ts_source.json=ts_source.json` 将来源文件置于 GJF 同目录；采集路径使用 `connectivity_inputs.json` 每个输入的 `collect`，它与 `%chk` 使用同一个文件名来源。执行前校验来源包摘要和输入内容，执行后核对第一帧坐标。修改绑定输入需要重新生成。普通未绑定 Gaussian 输入仍可使用，但不能声称其 TS 来源已经验证。

先运行位移优化。对每个优化后的端点建立材料，用 `chemical.gaussian-evidence` 解析其 Opt+Freq 并明确声明无约束。向 `chemical.displacement-check@1` 提供 `material`、TS 的 `evidence`、模式 `coordinates`、`reactant`、`product` 以及以下格式的 `study`：

```json
{
  "schema_version": "chemical-displacement-study/1",
  "branches": [
    {"direction": "plus", "amplitude_angstrom": 0.05,
     "endpoint": {"material": {}, "minimum_evidence": {}}},
    {"direction": "minus", "amplitude_angstrom": 0.05,
     "endpoint": {"material": {}, "minimum_evidence": {}}}
  ]
}
```

每种幅度都要包含正负方向；`endpoint` 使用通用 IRC 检查的端点契约。最低点证据的 `optimization.start_coordinates` 必须匹配重新计算的位移结构。检查原子身份、电荷/自旋、方法/基组、无约束收敛、频率和几何对应的化学身份。正负方向允许交换 R/P；不同幅度必须得到一致的分配。同盆地或幅度敏感结果为“尚不能确定”。允许仅一个幅度，但会明确未检查幅度敏感性。

对关键路径或位移结果不明确的情况，运行准备好的双向短 IRC，再优化各方向的**最后一个已接受路径点**，不能替换成 TS 初猜或失败校正器的试探结构。将端点最低点证据附到对应 IRC 证据的 `endpoint`，调用 `chemical.irc-check@1 --policy endpoint_relaxation`。只有正常结束、路径从绑定 TS 出发并下降、端点优化起点完全对应且连接 R/P 的证据齐全时，才允许达到 MaxPoints 的短路径通过。默认 `--policy strict` 仍要求完整路径且未触及点数上限。错误终止的路径保留已接受点供诊断恢复，但不会通过这两种策略；独立 restart 段也不能证明来自 TS，需要正确拼接并复核完整来源。

结果分别标记 `mode_displacement_endpoint_support`、`short_irc_with_endpoint_optimization`、`complete_irc`。解析成功、cclib 的 `optdone`、Gaussian 正常结束都不等于上述科学结论。普通优化可能越过浅中间体，位移端点支持不能当作 IRC 或机理唯一性的证明。

当前生成器支持自包含的方法/基组，使用显式已验证 TS 坐标重新 CalcFC。溶剂、附加色散、外部基组/ECP 等设置需要显式支持；检测到不支持的设置会拒绝生成，不会静默丢弃。当前流程不认证二进制 checkpoint 的 Hessian 复用；旧 checkpoint 准备器也不会自动获得 TS 来源认证。

重试是有界工作流指导，尚非自动重试调度器：首次触及 MaxPoints 就检查端点，每个分支最多三次有依据的尝试，记录改动和原因。只有明确的外部执行故障才允许原样重试。语法错误先修输入，解析冲突先查原始日志，不要直接重算；提交状态不明时先核对已有 Job。只有端点检查与优化仍不能判断时才延长 IRC。
