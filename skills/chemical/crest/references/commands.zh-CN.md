# 操作入口

通过通用 executor 准备请求，再由 `job_start` 提交。下表入口和 CLI 路径相对于本 Skill 目录，输出路径相对于 Job 工作目录。

| Executor | 入口 | CLI | 输入角色 | 主要输出 |
| --- | --- | --- | --- | --- |
| `chemical.crest-ensemble@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `material`, `run` | `results/result.json`, `results/refinement.json` |
| `chemical.ensemble-select@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `ensemble` | `results/result.json`, `results/refinement.json` |
| `chemical.complex-sample@1` | `scripts/ensemble.py` | `scripts/ensemble_cli.py` | `input` | `results/result.json`, `results/refinement.json` |
| `chemical.crest@1` | `scripts/crest_run.py` | `scripts/crest_cli.py` | `material` | `results/result.json`, `results/crest.out`, `results/crest_conformers.xyz`, `results/crest_best.xyz`, `results/crest.energies` |

输入格式、必要参数、科学检查与恢复方法见下列操作合同；根据当前操作选择读取：

- [crest backend contract](crest_backend_contract.zh-CN.md)
- [crest ensemble](crest_ensemble.zh-CN.md)

准备命令中的 `--executor` 和 `--version` 使用上表值，`--input role=path` 使用实际输入角色。执行目标继承当前任务，不在领域 Skill 中指定 `--platform` / `--scheduler-entry`。仅当合同未说明某个选项时，查询该 executor 的 `--help`。

准备失败时先修正输入、参数或软件绑定；准备成功不表示计算已执行。提交超时先核实已有 Job 与回执。计算失败时收集可用输出，按操作合同检查原因后再决定重试；不要把失败输出当作通过验证的结果。

`primary.parsing_status=limited` 时使用 `scripts/crest_io.py`，传入 `--directory`、
`--material`、`--run`、`--max-members` 和新的 `--output` 文件；具体见
[重解析已保留输出](crest_ensemble.zh-CN.md#重解析已保留输出)。这是收集证据的纯解析，
不新增 executor，也不再次运行原生搜索。
