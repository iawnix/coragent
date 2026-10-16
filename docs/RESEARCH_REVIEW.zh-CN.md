# Research Review

`Research Review`（`research-review/1`）是从当前 Research State 计算出的短期审查视图。它不是新的记忆库，也不是面向用户的 `chemical.research-report` 交付文档。

```text
Research State
  ├─ Node / Result / Job / Artifact
  └─ Research Snapshot（完整读取投影）
       ↓
  Deterministic Research Review（上下文投影）
       ↓
  Agent + Task Controller
```

Review 包含：

- `state_digest`：本次审查覆盖的状态版本；状态变化后，旧 Review 不能被当作当前事实。
- `findings`：当前范围内记录的 Node、Result 和 Job 摘要。
- `contradictions`：已有的 review notice、关系诊断、Job 失败或执行冲突。
- `uncertainties`：仍在运行、未收集完整、没有 assessment 的研究项。
- `limitations`：范围或传输预算造成的省略、待处理的运行时投影、Result 的限制。
- `follow_up`：需要 Agent 进一步读取或处理的建议，带有原始引用。

Review 只总结已记录的事实。它不把 Job 成功提升为科学结论，不替 Node 关闭问题，不授予写权限，也不发起计算。

上下文管理器在新的研究范围或需要重新建立研究背景的输入边界上调用 `research.read(view="review")`，默认注入压缩后的 Review，并保留 `review_id`、`review_digest` 和 `state_digest`。新的 Monitor 事件批次、Job 终态或收集、Result/Artifact 写入，以及用户改变研究要求时，才会建立新的 Review 边界；普通日志、运行中间状态和普通工具回合复用已有锚点。多个 Monitor 事件在 admission 层合并，同一 `state_digest` 不重复综合。当 Review 标记为 `pending` 时，当前模型可进行一次无工具、限长的综合；综合结果只作为运行时上下文缓存，必须引用 Review 的 `source_refs`，不会写入 Research Memory。失败时继续使用确定性 Review。完整快照和具体 Node、Result、Job 仍通过原有读取工具获得。Review 只接受并输出 `research-review/1`，不会把读取凭据放进模型上下文。

Task Controller 仍只负责任务状态和是否允许 `next_run`。Review 不创建第二个调度器。Monitor 的多个 terminal 事件由已有 admission 合并；暂停、等待或取消状态不会因为 Review 自动获得运行权限。

`chemical.research-report` 继续负责最终用户报告、图表和轨迹。化学领域 Skill 可以把 Review 当作证据入口，但结构、过渡态或其他领域判断必须由对应 Skill 和原始 Artifact 完成。
