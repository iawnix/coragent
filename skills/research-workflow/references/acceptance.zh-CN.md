# 任务验收与交付

报告已保存，只证明留存了报告，不证明用户目标已经满足。保留原有每项验收要求；只有新的用户要求才能通过 `refine` 修改。用 `task_read` 获取 `workspace_id`、`user_task_id`、`requirements_revision` 和当前 criteria。

逐项检查领域证据，再用 `artifact_create` 保存固定 JSON 评估文件（`name`、`media_type="application/json"`、`content` 为 JSON 字符串），也可注册已有评估文件。示例 ID 必须替换成实际返回值：

```json
{
  "schema_version": "task-assessment/1",
  "workspace_id": "workspace",
  "user_task_id": "task_1",
  "requirements_revision": 1,
  "criterion_id": "connection",
  "status": "undetermined",
  "reason": "尚未证实用户要求的端点连接。",
  "checks": [{
    "method": "reasoned",
    "status": "undetermined",
    "reason": "现有计算不能确认两端结构。",
    "evidence_refs": ["result_1", "art_1"]
  }],
  "conflicts": []
}
```

`method=programmatic` 表示实际执行验证器且保留输出；`reasoned` 表示明确说明依据的推理判断。填写标签本身不能证明验证器已运行。科学检查由领域 Skill 定义；控制器验证归属、固定引用、状态一致性和 Result 待复核提示，不能从文字中证明科学结论为真。

每个 check 必须有状态、理由和固定的 `art_N`/`result_N` 支持证据，并列入 completion 的 evidence_refs。不能用评估文件本身作为自己的支持证据。检查项为 1–64 项，文件不超过 100000 UTF-8 字节。必须声明 `conflicts`；存在未解决冲突时为 `undetermined`；否则任一检查为 `unmet` 则整项为 `unmet`，其次任一 `undetermined` 则整项为 `undetermined`，只有全部满足才为 `met`。

以当前 `expected_revision` 调用 `task_update action=propose_completion`，为每项 criterion 恰好提供一个条目：

```json
{
  "expected_revision": 4,
  "action": "propose_completion",
  "completion_outcome": "partial",
  "completion": [{
    "criterion_id": "connection",
    "status": "undetermined",
    "assessment_ref": "art_2",
    "evidence_refs": ["result_1", "art_1"]
  }],
  "stop_basis": {
    "kind": "search_exhausted",
    "reason": "约定的有限搜索已耗尽，已留存尝试与剩余限制。",
    "evidence_refs": ["art_3"]
  }
}
```

- `full`：所有条目均为 `met`，不传 `stop_basis`。科学否定结果可以满足“完成调查并报告”的要求，不能满足“建立连接”或“成功完成计算”的要求。
- `partial`：保留至少一项 `unmet`/`undetermined`，提供停止依据。`budget_exhausted`/`search_exhausted` 需固定证据说明适用限制与已耗尽的工作；`user_requested` 需真实 `source_submission_ids` 和引用用户停止并部分交付指令的 `source_text`。停滞、单个候选失败或报告存在都不是停止依据。
- 仍有可推进的授权工作时使用 `progress`；暂时缺少必要前提时使用 `block`，均不算完成。

申请收尾前先解决仍未终止的 Jobs。任务先进入 `completing`；只有最终答复已记录且证据复核通过，才变为 `completed` 或 `partial`。要求版本变化使旧评估失效。交付失败恢复保留原结果，只允许只读检查和最终答复，沿用已有回执，不能重复外发消息或计算。证据变化或过期则回到 active 重新评估。用户明确继续时可重新打开 partial，历史验收仍保留。
