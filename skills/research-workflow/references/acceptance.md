# Task acceptance and delivery

A report's existence proves retention, not satisfaction of the user's objective. Keep each original criterion until a new user instruction changes it with `refine`. Read `task_read` for `workspace_id`, `user_task_id`, `requirements_revision` and current criteria.

For each criterion, inspect the domain evidence and create a fixed JSON Artifact with `artifact_create` (`name`, `media_type="application/json"`, `content` containing serialized JSON), or register an existing assessment file. Use actual returned IDs:

```json
{
  "schema_version": "task-assessment/1",
  "workspace_id": "workspace",
  "user_task_id": "task_1",
  "requirements_revision": 1,
  "criterion_id": "connection",
  "status": "undetermined",
  "reason": "The requested endpoint connection has not been established.",
  "checks": [{
    "method": "reasoned",
    "status": "undetermined",
    "reason": "The retained calculation does not establish both endpoints.",
    "evidence_refs": ["result_1", "art_1"]
  }],
  "conflicts": []
}
```

`method` is `programmatic` for an executed validator with retained outputs, or `reasoned` for an explicit evidence-based judgment. A label is not proof that a validator ran. Domain Skills define scientific checks; the controller verifies scope, fixed references, status consistency and current Result review notices. It cannot certify scientific truth from prose.

Every check needs status, reason and fixed `art_N`/`result_N` evidence included in the completion entry. An assessment cannot cite itself as support. Use 1–64 checks and keep the file under 100000 UTF-8 bytes. Always declare `conflicts`; unresolved conflicts imply `undetermined`. Otherwise any `unmet` check makes the criterion `unmet`, then any `undetermined` check makes it `undetermined`; only all `met` checks permit `met`.

Submit `task_update action=propose_completion` with the current `expected_revision`, `completion_outcome`, and exactly one entry per criterion:

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
    "reason": "The agreed bounded search has exhausted its documented alternatives.",
    "evidence_refs": ["art_3"]
  }
}
```

- `full`: every criterion is `met`; omit `stop_basis`. A negative scientific finding may satisfy a criterion asking for an investigation/report, but cannot satisfy a criterion requiring an established connection or successful calculation.
- `partial`: retain at least one `unmet`/`undetermined` criterion and a stopping basis. `budget_exhausted`/`search_exhausted` need fixed evidence of the applicable limit and exhausted work. `user_requested` needs actual `source_submission_ids` and `source_text` quoting the user's instruction to stop with a partial deliverable. A stall, a failed candidate or a report alone is not a stopping basis.
- Progress while useful authorized work remains uses `progress`; a temporary unmet prerequisite uses `block`. Neither is completion.

Settle outstanding Jobs before proposing closure. The task enters `completing`; only a recorded final response and successful evidence recheck close it as `completed` or `partial`. Revisions invalidate older assessments. Delivery recovery retains the outcome and permits read-only checks/final response; reuse receipts and never resend external messages or restart calculations. A changed/stale evidence recheck returns the task to active reassessment. Explicit user resume reopens a partial task and retains its previous acceptance in history.
