# 局部结构诊断

[English](local_diagnostics.md)

`chemical.local-diagnostics@1` 使用 structure（RDKit/NumPy），可独立检查种子、失败
优化帧、NEB image 或构象，不需要产物、TS 或流程状态；电子分析需独立证据。

`chemical-local-diagnostics-input/1` 包含 material（内嵌 chemical-material/1，
1–256 个有坐标原子）及 reaction_center（不重复的本地原子 ID）。可选 spectators 与
中心不重叠。可选 reference 必须同时给出从**当前 material ID 到 reference ID**的
完整 mapping，保持元素和同位素。ID 不是 XYZ 行号。

可选字段：

- coordinates：最多 256 条，例如
  `{"id":"forming","atoms":["atom_1","atom_2"],"minimum":1.5,"maximum":2.5}`。
  2/3/4 原子分别为距离/角/二面角，单位 Å/度。只观察时同时省略上下限。
  距离非负，角 0–180°，二面角 −180–180°；二面角下限大于上限表示跨周期区间。
  退化坐标为 null。
- contact_scale：0.1–1.5，默认 0.75 乘 RDKit 共价半径之和。
- allowed_contacts：最多 512 对 ID；用户允许的短接触仍保留并标注。

chemical-local-diagnostics-result/1 包含每个中心原子的最近六个邻居、涉及中心的
短接触、内部坐标和声明区间检查。有 reference 时分别做重原子和中心的 Kabsch 纯旋转
拟合，给出逐原子位移；只有两个中心均不共线时才报告按中心对齐的旁观原子 RMSD。
不镜像对齐，不逐片段独立对齐。电荷/自旋/态声明单独比较，一致不证明波函数相同。
短接触只是邻近启发式，不推断键/价态、不认证 TS 或机制，scientific_verdict 为 not_assessed。

```text
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --environment local --executor chemical.local-diagnostics --version 1 --input input=<work_dir>/diagnostics.json --input-artifact <input-ref> --output <work_dir>/diagnostics-request.json
```

替换占位符，提交返回请求/摘要与 node_id，随后收集 results/result.json；结果保留
规范化输入/材料摘要与原输入文件 SHA-256。可结合[轨迹工具](../../report/references/research_tools.zh-CN.md)
比较帧，并按[搜索诊断](../../method-selection/references/search_recovery.zh-CN.md)解释观察。
