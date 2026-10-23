import { resolveTaskSelection } from "./execution-selection.mjs";

const key = target => `${target.platform}/${target.scheduler_entry}`;
const fail = message => { throw Object.assign(new Error(message), { code: "execution_plan_invalid" }); };

export async function resolveExecutionPolicy(kernel, policy, selection, sources) {
  const selections = policy ? await Promise.all(policy.placements.map(placement =>
    resolveTaskSelection(kernel, { execution_target: placement.target, execution_intent: placement.intent }, sources))) : [selection];
  if (new Set(selections.map(item => key(item.target))).size !== selections.length) fail("Duplicate policy placement");
  if (!selections.some(item => key(item.target) === key(selection.target))) fail("Default placement must be allowed by the policy");
  selections.sort((a, b) => Number(key(b.target) === key(selection.target)) - Number(key(a.target) === key(selection.target)));
  return { selections, max_in_flight: policy?.max_in_flight ?? 1, max_attempts: policy?.max_attempts ?? 100,
    automatic_placement: policy?.automatic_placement ?? false };
}

export async function resolveExecutionPlan(kernel, draft, policy, previous, jobs) {
  const items = [], assigned = new Map();
  for (const item of draft.items) {
    let selection = item.target
      ? await kernel.execute_command("job_resolve_target", { target: item.target }) : policy.selections[0];
    let placement_reason = "Explicit placement or policy default";
    if (item.candidates) {
      if (!policy.automatic_placement || item.target || !item.backend) fail("Automatic placement requires permission, candidates and a software backend, without a fixed target");
      const previousItem = previous?.items.find(row => row.id === item.id);
      const resolvedCandidates = [];
      for (const target of item.candidates) {
        const resolved = await kernel.execute_command("job_resolve_target", { target });
        if (!policy.selections.some(allowed => key(allowed.target) === key(resolved.target)
          && allowed.route_digest === resolved.route_digest)) fail("Candidate is outside the pinned policy");
        resolvedCandidates.push(resolved);
      }
      if (previousItem && (previousItem.completion || jobs.some(job => job.execution_item?.id === item.id))) {
        if (!resolvedCandidates.some(row => key(row.target) === key(previousItem.selection.target)))
          fail("Submitted items cannot be moved outside their candidate set");
        selection = previousItem.selection;
        placement_reason = previousItem.placement_reason;
      } else {
        const configured = await kernel.execute_command("job_platforms", {});
        const candidates = [];
        for (const resolved of resolvedCandidates) {
          const entry = configured.platforms[resolved.target.platform].schedulers[resolved.target.scheduler_entry];
          if (!entry.software.includes(item.backend)) continue;
          if (["cpus", "memory_mb", "gpus"].some(field => entry.limits?.[field] !== undefined
            && item.resources[field] > entry.limits[field])) continue;
          const observation = await kernel.execute_command("job_resources", { execution_target: resolved.target });
          const allocated = assigned.get(key(resolved.target)) || { cpus: 0, memory_mb: 0 };
          if (observation.available && !observation.scheduler_observation?.paused
            && !observation.scheduler_observation?.stale && !item.resources.gpus
            && observation.free?.cpus - allocated.cpus >= item.resources.cpus
            && observation.free?.memory_mb - allocated.memory_mb >= item.resources.memory_mb)
            candidates.push({ resolved, observation, free_cpus: observation.free.cpus - allocated.cpus });
        }
        candidates.sort((a, b) => b.free_cpus - a.free_cpus
          || key(a.resolved.target).localeCompare(key(b.resolved.target)));
        if (!candidates.length) fail("No permitted candidate has known sufficient resources and the required software binding");
        selection = candidates[0].resolved;
        placement_reason = `Available capacity observed at ${candidates[0].observation.observed_at}; software ${item.backend} configured; preparation still verifies readiness`;
      }
    }
    if (!policy.selections.some(allowed => key(allowed.target) === key(selection.target)
      && allowed.route_digest === selection.route_digest)) fail("Item placement is outside the pinned policy");
    const allocated = assigned.get(key(selection.target)) || { cpus: 0, memory_mb: 0 };
    assigned.set(key(selection.target), { cpus: allocated.cpus + item.resources.cpus,
      memory_mb: allocated.memory_mb + item.resources.memory_mb });
    items.push({ id: item.id, work_id: item.work_id, selection, depends_on: item.depends_on || [],
      input_artifact_ids: item.input_artifact_ids || [], resources: item.resources,
      placement_reason, backend: item.backend ?? null, completion: null });
  }
  if (new Set(items.map(item => item.id)).size !== items.length
    || new Set(items.map(item => item.work_id)).size !== items.length) fail("Item IDs and work IDs must be unique");
  const byId = new Map(items.map(item => [item.id, item])), visiting = new Set(), visited = new Set();
  const visit = id => {
    if (!byId.has(id)) fail("Unknown dependency: " + id);
    if (visiting.has(id)) fail("Execution dependencies contain a cycle");
    if (visited.has(id)) return;
    visiting.add(id);
    for (const dependency of byId.get(id).depends_on) visit(dependency);
    visiting.delete(id); visited.add(id);
  };
  for (const item of items) visit(item.id);
  for (const old of previous?.items || []) {
    const current = byId.get(old.id);
    const submitted = jobs.some(job => job.execution_item?.id === old.id);
    if ((submitted || old.completion) && (!current || JSON.stringify({ ...current, completion: null })
      !== JSON.stringify({ ...old, completion: null }))) fail("Submitted or completed items cannot be changed or removed");
    if (current) current.completion = old.completion;
  }
  return { revision: (previous?.revision || 0) + 1, items };
}

export function executionItemContext(task, id) {
  const pinned = selection => ({ target: selection.target, route_digest: selection.route_digest });
  const policy = { max_in_flight: task.execution_policy.max_in_flight, max_attempts: task.execution_policy.max_attempts };
  if (!task.execution_plan) return { selection: pinned(task.execution_selection), policy };
  const item = task.execution_plan.items.find(row => row.id === id);
  if (!item) fail("Select an execution item before preparation or submission");
  if (item.completion) fail("The execution item is already complete");
  const inputs = [...item.input_artifact_ids];
  for (const dependency of item.depends_on) {
    const predecessor = task.execution_plan.items.find(row => row.id === dependency);
    if (!predecessor.completion) fail("Dependency has not been collected and validated: " + dependency);
    inputs.push(...predecessor.completion.artifact_ids);
  }
  return { selection: pinned(item.selection), policy,
    item: { id: item.id, work_id: item.work_id, plan_revision: task.execution_plan.revision,
      input_artifact_ids: [...new Set(inputs)], resources: item.resources,
      ...(item.backend ? { backend: item.backend } : {}) } };
}

export function projectExecutionPlan(task, jobs) {
  if (!task.execution_plan) return null;
  return { revision: task.execution_plan.revision, active_item_id: task.active_execution_item,
    items: task.execution_plan.items.map(item => {
      const job = jobs.findLast(row => row.execution_item?.id === item.id);
      return { id: item.id, target: item.selection.target, work_id: item.work_id,
        state: item.completion ? "succeeded" : job ? (job.state === "succeeded"
          ? job.collection_state === "complete" ? "validating" : "collecting" : job.state) : item.depends_on.some(id =>
          !task.execution_plan.items.find(row => row.id === id).completion) ? "blocked" : "ready",
        job_id: job?.job_id ?? null, collection_state: job?.collection_state ?? null };
    }) };
}
