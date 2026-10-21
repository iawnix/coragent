# 操作入口

通过通用 executor 准备请求，再由 `job_start` 提交。下表入口和 CLI 路径相对于本 Skill 目录，输出路径相对于 Job 工作目录。

| Executor | 入口 | CLI | 输入角色 | 主要输出 |
| --- | --- | --- | --- | --- |
| `chemical.resolve@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/resolve.json` |
| `chemical.resolve-candidates@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | `candidates` | `results/resolve.json` |
| `chemical.inspect@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/inspect.json` |
| `chemical.seed@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/seed.json` |
| `chemical.reaction@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | — | `results/reaction.json` |
| `chemical.compare@1` | `scripts/reaction/prepare.py` | `scripts/reaction/cli.py` | `target`, `actual` | `results/comparison.json` |
| `chemical.material@1` | `scripts/materials/material.py` | `scripts/materials/material_cli.py` | `material` | `results/material.json`, `results/atom_order.json`, `results/source.txt`, `results/geometry.xyz` |
| `chemical.map-candidates@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `left`, `right` | `results/result.json` |
| `chemical.conformer-compare@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `left`, `right` | `results/result.json` |
| `chemical.reorder-tensors@1` | `scripts/geometry/analysis.py` | `scripts/geometry/analysis_cli.py` | `tensors`, `order` | `results/result.json` |
| `chemical.local-diagnostics@1` | `scripts/diagnostics/diagnostics_job.py` | `scripts/diagnostics/diagnostics_cli.py` | `input` | `results/result.json` |

输入格式、必要参数、科学检查与恢复方法见下列操作合同；根据当前操作选择读取：

- [local diagnostics](local_diagnostics.zh-CN.md)
- [material input](material_input.zh-CN.md)
- [name resolution](name_resolution.zh-CN.md)
- [reaction mapping](reaction_mapping.zh-CN.md)
- [script layout](script_layout.zh-CN.md)
- [structure analysis](structure_analysis.zh-CN.md)
- [structure input](structure_input.zh-CN.md)

准备命令中的 `--executor` 和 `--version` 使用上表值，`--input role=path` 使用实际输入角色。执行目标继承当前任务，不在领域 Skill 中指定 `--target`。仅当合同未说明某个选项时，查询该 executor 的 `--help`。

准备失败时先修正输入、参数或软件绑定；准备成功不表示计算已执行。提交超时先核实已有 Job 与回执。计算失败时收集可用输出，按操作合同检查原因后再决定重试；不要把失败输出当作通过验证的结果。
