# 模型工具索引

由 scripts/update_public_contract.mjs 生成。名称、描述和参数由运行时直接提供给模型；此索引不注册工具。模型工具与后端命令使用同一名称，内部命令不自动对模型开放。终端 slash command 是独立的用户入口。

```text
task_begin
task_read
task_update
research_read
research_search
research_create
research_update
research_result
job_start
job_status
job_collect
job_cancel
job_probe
job_platforms
job_resources
job_reconcile
artifact_register
artifact_create
artifact_read
```

Research Memory 保存原始要求、研究 Node、不可变 Result 和显式关系。Job Manager 负责执行，Artifact Store 保存材料与来源。研究记录更新不授予工具权限，也不触发 next_run。
