# 证据与结论

检查实际材料后再记录科学观察。用 `observation` 保存测量事实，用 `conclusion` 表达解释，用 `limitations` 说明未决条件。失败、否定和未定结果也可以发布；用户要求本身不证明科学结论。

按用途选择引用字段，并使用实际返回的完整 ID：

| 字段 | 用途与允许的引用 |
| --- | --- |
| research_create.source_refs | 原始用户需求；只接受 user_* 消息。 |
| research_create.input_refs | 背景引用；接受已有 Node、Result、用户消息、笔记、运行时记录、Job、收集回执和已验证 Artifact。 |
| research_result.inputs | 推导结论实际使用的固定材料；只接受已有 Result 和已验证 Artifact。没有此类输入时省略。 |
| research_result.evidence_refs | 支持性引用；允许类型与 Node 的 input_refs 相同，包括用户消息和执行记录。需求来源不等于科学证明。 |
| research_result.files[].artifact_ref | 交付文件；必须是已验证 Artifact 引用，不能是可修改路径、Job ID 或回执。 |
| research_result.check_refs | 特定检查的依据；接受已验证 Artifact 或收集回执，不接受 Job ID。允许检查未得出确定结论。 |
| create/update/result 的 subjects | 命名角色；值只接受已有 Result 或已验证 Artifact。 |
| research_update.assessment_ref | 同一 Node 下已有的 Result 或由 Agent 撰写的笔记/记录。 |
| research_result.supersedes | 同一 Node 下需要明确修正的旧 Result。 |

根据用户请求解析出候选结构时，可在 evidence_refs 中引用结构 Artifact 和原始用户消息。不要把用户消息放进 inputs。例如（将所有示例 ID 替换为实际返回的引用）：

```json
{"node_id":"node_...","conclusion":"已解析出候选结构，反应机理仍未确定。","evidence_refs":["art_...","user_..."]}
```

## 修订与复核

Result 发布后不可覆盖。纠正时发布新的 Result，通过 `supersedes` 指向同一 Node 的旧结论，并说明证据或解释变化。新 Result 不会自动取代当前综合判断；按需设置 `as_assessment`。检查 `result_saved` 与 `assessment_selected`，区分发布成功和综合判断选择成功。沿依赖引用复核下游结论，保留仍有效的材料与竞争解释。

Job 输出的生产来源通过 `job_collect` 保存；不要将原始输出重写为无来源文本。准备、提交和收集见[Job 与材料流程](../../research-workflow/references/jobs-and-artifacts.zh-CN.md)。
