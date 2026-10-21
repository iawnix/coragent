# 操作入口

通过通用 executor 准备请求，再由 `job_start` 提交。下表入口和 CLI 路径相对于本 Skill 目录，输出路径相对于 Job 工作目录。

| Executor | 入口 | CLI | 输入角色 | 主要输出 |
| --- | --- | --- | --- | --- |
| `chemical.gaussian@1` | `scripts/run.py` | `scripts/cli.py` | `geometry` | `results/result.json`, `results/geometry.xyz` |
| `chemical.gaussian-input@1` | `scripts/run.py` | `scripts/cli.py` | `input` | `results/result.json`, `results/geometry.xyz`, `results/gaussian.out`, `results/parsed.json` |
| `chemical.electronic-gaussian@1` | `scripts/electronic.py` | `scripts/electronic_cli.py` | `input` | `results/result.json` |
| `chemical.state-tracking@1` | `scripts/electronic.py` | `scripts/electronic_cli.py` | `input` | `results/result.json` |

输入格式、必要参数、科学检查与恢复方法见下列操作合同；根据当前操作选择读取：

- [electronic states](electronic_states.zh-CN.md)
- [gaussian validation](gaussian_validation.zh-CN.md)
- [l101 input guide](l101_input_guide.zh-CN.md)
- [relaxed scans](relaxed_scans.zh-CN.md)

准备命令中的 `--executor` 和 `--version` 使用上表值，`--input role=path` 使用实际输入角色。执行目标继承当前任务，不在领域 Skill 中指定 `--target`。仅当合同未说明某个选项时，查询该 executor 的 `--help`。

准备失败时先修正输入、参数或软件绑定；准备成功不表示计算已执行。提交超时先核实已有 Job 与回执。计算失败时收集可用输出，按操作合同检查原因后再决定重试；不要把失败输出当作通过验证的结果。
