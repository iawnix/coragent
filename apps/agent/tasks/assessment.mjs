// Domain-neutral acceptance contract. Validators/Skills author the checks;
// this boundary verifies their scope, status and fixed supporting references.
const statuses = new Set(["met", "unmet", "undetermined"]);
const requireAssessment = (ok, message) => {
  if (!ok) throw Object.assign(new Error(message), { code: "task_assessment_invalid" });
};

export async function verifyAssessment(kernel, task, item, verifyEvidence, ctx) {
  requireAssessment(/^art_[1-9][0-9]*$/.test(item.assessment_ref || ""), "Each criterion needs a fixed JSON assessment Artifact");
  const artifact = await kernel.execute_command("artifact.read", { artifact_id: item.assessment_ref, limit: 100000 });
  requireAssessment(!artifact.next_offset, "Assessment exceeds 100000 bytes; keep checks concise and reference supporting Artifacts");
  let assessment;
  try { assessment = JSON.parse(artifact.content); } catch { requireAssessment(false, "Assessment must be task-assessment/1 JSON"); }
  requireAssessment(assessment && assessment.schema_version === "task-assessment/1"
    && assessment.workspace_id === task.workspace_id && assessment.user_task_id === task.user_task_id
    && assessment.requirements_revision === task.requirements_revision
    && assessment.criterion_id === item.criterion_id, "Assessment scope or requirements revision does not match the current task");
  requireAssessment(task.criteria.some(c => c.id === item.criterion_id), "Unknown criterion_id");
  requireAssessment(statuses.has(assessment.status) && assessment.status === item.status, "Assessment and criterion statuses must agree");
  requireAssessment(typeof assessment.reason === "string" && assessment.reason.trim(), "Assessment needs a reason");
  requireAssessment(Array.isArray(assessment.checks) && assessment.checks.length > 0 && assessment.checks.length <= 64,
    "Assessment needs 1..64 explicit checks");
  requireAssessment(Array.isArray(assessment.conflicts), "Assessment must declare unresolved conflicts (an empty array when none)");
  for (const check of assessment.checks) {
    requireAssessment(check && statuses.has(check.status) && typeof check.reason === "string" && check.reason.trim()
      && ["programmatic", "reasoned"].includes(check.method), "Each check needs status, method and reason");
    requireAssessment(Array.isArray(check.evidence_refs) && check.evidence_refs.length > 0
      && check.evidence_refs.every(ref => typeof ref === "string" && /^(art|result)_[1-9][0-9]*$/.test(ref)
        && item.evidence_refs?.includes(ref) && ref !== item.assessment_ref), "Check evidence must be listed fixed Results/Artifacts, not the assessment itself");
  }
  const aggregate = assessment.conflicts.length ? "undetermined"
    : assessment.checks.some(c => c.status === "unmet") ? "unmet"
      : assessment.checks.some(c => c.status === "undetermined") ? "undetermined" : "met";
  requireAssessment(assessment.status === aggregate, "Criterion status conflicts with its checks or unresolved conflicts");
  const identities = await verifyEvidence([...new Set([...item.evidence_refs, item.assessment_ref])], ctx,
    { completion: true, current: item.status === "met", userTaskId: task.user_task_id });
  return { ...item, reason: assessment.reason, checks: assessment.checks, conflicts: assessment.conflicts,
    requirements_revision: task.requirements_revision, evidence_identities: identities };
}

export function checkCompletion(task, params) {
  const ids = params.completion?.map(item => item.criterion_id) || [];
  if (ids.length !== task.criteria.length || new Set(ids).size !== ids.length
    || task.criteria.some(c => !ids.includes(c.id)))
    throw Object.assign(new Error("Assess every current criterion exactly once"), { code: "task_completion_incomplete" });
  const allMet = params.completion.every(item => item.status === "met");
  if (!["full", "partial"].includes(params.completion_outcome) || (params.completion_outcome === "full") !== allMet)
    throw Object.assign(new Error("Full completion requires every criterion met; partial completion must retain unmet or undetermined criteria"), { code: "task_completion_outcome_invalid" });
  if (params.completion_outcome === "partial" && (!params.stop_basis?.reason?.trim()
    || !["user_requested", "budget_exhausted", "search_exhausted"].includes(params.stop_basis.kind)))
    throw Object.assign(new Error("Partial completion needs an evidenced stopping basis; progress reports do not end a task"), { code: "task_partial_basis_required" });
}
