import shared from "../../../contracts/commands/shared.json" with { type: "json" };

const TOOL_ROWS = [
  ["task_begin", "deterministic_runtime"],
  ["task_read", "deterministic_runtime"],
  ["task_update", "deterministic_runtime"],
  ["research_read", "deterministic_workspace"],
  ["research_search", "deterministic_workspace"],
  ["research_create", "deterministic_workspace"],
  ["research_update", "deterministic_workspace"],
  ["research_result", "deterministic_workspace"],
  ["job_start", "execution_runtime"],
  ["job_status", "execution_runtime"],
  ["job_collect", "execution_runtime"],
  ["job_cancel", "execution_runtime"],
  ["job_probe", "execution_runtime"],
  ["job_reconcile", "execution_runtime"],
  ["artifact_register", "deterministic_artifact"],
  ["artifact_create", "deterministic_artifact"],
  ["artifact_read", "deterministic_artifact"],
];

// Semantic Harness names are the stable interface exposed to Agents. The
// Tool factories expose semantic names directly and are never duplicated in inventory.
export const PUBLIC_TOOL_NAMES = Object.freeze(TOOL_ROWS.map(([name]) => name));

export const PUBLIC_TOOL_EXECUTION = Object.freeze(Object.fromEntries(
  TOOL_ROWS.map(([name, execution]) => [name, execution]),
));

// Canonical Harness metadata. Tool implementations remain transport adapters;
// this registry is the shared authority/effect/replay contract used by Hosts,
// audits, and future transports.
export const PUBLIC_TOOL_METADATA = Object.freeze({
  task_begin: Object.freeze({ authority: "task_control", effect: "task_write", replay: "idempotent", phase: "advance" }),
  task_read: Object.freeze({ authority: "task_control", effect: "read", replay: "safe", phase: "orient" }),
  task_update: Object.freeze({ authority: "task_control", effect: "task_write", replay: "idempotent", phase: "advance" }),
  research_read: Object.freeze({ authority: "kernel_read", effect: "read", replay: "safe", phase: "orient" }),
  research_search: Object.freeze({ authority: "kernel_read", effect: "read", replay: "safe", phase: "orient" }),
  research_create: Object.freeze({ authority: "kernel_write", effect: "research_write", replay: "idempotent", phase: "advance" }),
  research_result: Object.freeze({ authority: "kernel_write", effect: "research_write", replay: "idempotent", phase: "interpret" }),
  research_update: Object.freeze({ authority: "kernel_write", effect: "research_write", replay: "idempotent", phase: "advance" }),
  job_start: Object.freeze({ authority: "execution_runtime", effect: "execution_control", replay: "never", phase: "execute" }),
  job_status: Object.freeze({ authority: "execution_runtime", effect: "read", replay: "safe", phase: "execute" }),
  job_collect: Object.freeze({ authority: "execution_runtime", effect: "result_collection", replay: "idempotent", phase: "interpret" }),
  job_cancel: Object.freeze({ authority: "execution_runtime", effect: "execution_control", replay: "idempotent", phase: "execute" }),
  job_probe: Object.freeze({ authority: "execution_runtime", effect: "read", replay: "safe", phase: "prepare" }),
  job_reconcile: Object.freeze({ authority: "execution_runtime", effect: "execution_control", replay: "idempotent", phase: "execute" }),
  artifact_register: Object.freeze({ authority: "artifact_runtime", effect: "artifact_write", replay: "idempotent", phase: "prepare" }),
  artifact_create: Object.freeze({ authority: "artifact_runtime", effect: "artifact_write", replay: "idempotent", phase: "prepare" }),
  artifact_read: Object.freeze({ authority: "artifact_runtime", effect: "read", replay: "safe", phase: "interpret" }),
});

const TOOL_NAME_PATTERN = /^[a-z][a-z0-9_]*$/u;
const METADATA_FIELDS = Object.freeze(["authority", "effect", "replay", "phase"]);
const METADATA_VALUES = Object.freeze({
  authority: new Set([
    "host_read", "kernel_read", "kernel_write", "runtime_read", "advisory_runtime",
    "execution_runtime", "research_write", "artifact_runtime", "external_side_effect", "task_control",
  ]),
  effect: new Set([
    "read", "research_write", "result_collection",
    "artifact_write", "execution_control", "external_write", "task_write",
  ]),
  replay: new Set(["safe", "idempotent", "never"]),
  phase: new Set(["orient", "advance", "prepare", "execute", "interpret"]),
});

/** Validate one executable tool at the Harness admission boundary. */
export function validateHarnessToolDefinition(tool, { source = "tool", requireCanonical = true } = {}) {
  if (!tool || typeof tool !== "object" || Array.isArray(tool)) {
    throw new TypeError(`${source} must be an object`);
  }
  if (typeof tool.name !== "string" || !TOOL_NAME_PATTERN.test(tool.name)) {
    throw new TypeError(`${source} has an invalid tool name`);
  }
  if (typeof tool.label !== "string" || !tool.label.trim()) {
    throw new TypeError(`${source} ${tool.name} has no label`);
  }
  if (typeof tool.description !== "string" || !tool.description.trim()) {
    throw new TypeError(`${source} ${tool.name} has no description`);
  }
  if (!tool.parameters || typeof tool.parameters !== "object" || Array.isArray(tool.parameters)) {
    throw new TypeError(`${source} ${tool.name} has no parameter schema`);
  }
  if (typeof tool.execute !== "function") {
    throw new TypeError(`${source} ${tool.name} has no execute function`);
  }
  const metadata = tool.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    throw new TypeError(`${source} ${tool.name} has no Harness metadata`);
  }
  const keys = Object.keys(metadata).sort();
  const expectedKeys = [...METADATA_FIELDS].sort();
  if (keys.length !== expectedKeys.length || keys.some((key, index) => key !== expectedKeys[index])) {
    throw new TypeError(`${source} ${tool.name} has invalid Harness metadata fields`);
  }
  for (const field of METADATA_FIELDS) {
    if (typeof metadata[field] !== "string" || !METADATA_VALUES[field].has(metadata[field])) {
      throw new TypeError(`${source} ${tool.name} has invalid Harness metadata ${field}`);
    }
  }
  const canonical = PUBLIC_TOOL_METADATA[tool.name];
  if (requireCanonical && canonical && METADATA_FIELDS.some((field) => metadata[field] !== canonical[field])) {
    throw new TypeError(`${source} ${tool.name} metadata does not match the canonical Harness contract`);
  }
  return tool;
}

export function createPublicToolContracts(Type) {
  const contracts = {
    task_begin: contract("task_begin", "Begin task", "Register a sustained assignment with actual user submission IDs, complete delivery criteria, an initial plan and next action. Requires no nonterminal task. Pins execution from source-bound execution_intent or the installation default; omit execution_target when unspecified. Read research-workflow before beginning.", Type.Unsafe(shared.tools.task_begin)),
    task_read: contract("task_read", "Read task", "Read the current user task, original requirements, revision, execution selection and next action. Reading does not resume paused or blocked work.", Type.Unsafe(shared.tools.task_read)),
    task_update: contract("task_update", "Update task", "Update the current task with expected_revision and the fields for the selected action. refine and apply_user_control require actual user submissions; internal events never authorize resume. propose_completion requires a fixed assessment for every criterion and an evidenced stopping basis for partial delivery. See research-workflow for lifecycle, execution correction and acceptance procedures.", Type.Unsafe(shared.tools.task_update)),
    research_read: contract("research_read", "Research memory", "Read a research overview or an exact Node, Result or record ref. Page omitted content; only fully returned Node fields establish a revision receipt for replacement. Returns Node work_dir for drafts without changing cwd. Reading does not create evidence dependencies or resume tasks.", Type.Unsafe(shared.tools.research_read)),
    research_search: contract("research_search", "Search research", "Search Nodes, Results and records. Empty query lists recent entries. kind selects node, result or an exact record kind; omit it to search all kinds. Search does not establish a field-read receipt or evidence relationship; read returned refs for details.", Type.Unsafe(shared.tools.research_search)),
    research_create: contract("research_create", "Create research Node", "Create a persistent research question and return its Node ID and work_dir. Requires goal. The first Node binds task entry/focus if none was selected. source_submission_ids resolves actual current user submissions; source_refs accepts only returned user_* refs, never IDs invented from submission numbers. Use research-memory for question granularity and relations.", Type.Unsafe(shared.tools.research_create), {executionMode: "sequential"}),
    research_update: contract("research_update", "Update research Node", "Append a note and optionally revise a Node. Read fields completely before replacing them; a revision conflict leaves the update unapplied. A note alone does not overwrite fields. Node status organizes research and does not cancel Jobs or complete a Task. assessment_ref selects an existing same-Node Result or agent record.", Type.Unsafe(shared.tools.research_update), {executionMode: "sequential"}),
    research_result: contract("research_result", "Publish research Result", "Publish an immutable, citable Node conclusion with observations, limitations and verified references. inputs accepts fixed Results/Artifacts; files accepts Artifacts. supersedes explicitly corrects a same-Node Result. as_assessment selects the synthesis subject to the read revision: with progress a conflict saves neither change; without progress publication can succeed while selection fails. Inspect result_saved and assessment_selected. See research-memory for evidence and corrections.", Type.Unsafe(shared.tools.research_result), {executionMode: "sequential"}),
    job_start: contract("job_start", "Start Job", "Submit a durable Job bound to the research node_id. Use a reviewed request_file with request_sha256, or prepared_ref; do not mix prepared and direct execution fields. Task execution bindings are enforced by the runtime. Submission returns job_id; an uncertain response requires reconciliation, not a fresh submission. See research-workflow for preparation and collection.", Type.Unsafe(shared.tools.job_start), { executionMode: "sequential", replay: "never" }),
    job_status: contract("job_status", "Job Status", "Observe an existing Job by job_id or event_id. Does not collect output or establish scientific validity. Respect the returned polling guidance; use task_update wait when no independent work remains. Collect terminal outputs with job_collect.", Type.Unsafe(shared.tools.job_status), { executionMode: "sequential" }),
    job_collect: contract("job_collect", "Collect Job", "Collect available Job outputs and logs with producer provenance, including partial or failed outputs. Does not rerun execution. Inspect output_validation and result_receipt.collection_state. artifacts supplies fixed file references; the collection receipt is evidence, not a Result input or file attachment.", Type.Unsafe(shared.tools.job_collect), { executionMode: "sequential" }),
    job_cancel: contract("job_cancel", "Cancel Job", "Request cancellation without deleting history or outputs. Inspect the returned state: unknown or pending does not confirm termination. Reconcile uncertain cancellation and collect available outputs after termination.", Type.Unsafe(shared.tools.job_cancel), { executionMode: "sequential" }),
    job_probe: contract("job_probe", "Probe Job", "Check configured execution-target infrastructure, input availability, connectivity and transfer/scheduler commands as applicable. Does not verify scientific software; use its targeted environment check.", Type.Unsafe(shared.tools.job_probe), { executionMode: "sequential" }),
    job_reconcile: contract("job_reconcile", "Reconcile Job", "Recover the existing Job receipt/status after uncertain dispatch or interrupted observation. Reuse the original job_id/event_id; this does not submit a new calculation. Inspect diagnostics if state remains unknown.", Type.Unsafe(shared.tools.job_reconcile), { executionMode: "sequential" }),
    artifact_register: contract("artifact_register", "Register Artifact", "Import an existing workspace file as a fixed Artifact and return its references and metadata. Use job_collect for raw Job outputs to retain producer provenance. Registration does not prove a scientific claim.", Type.Unsafe(shared.tools.artifact_register), { executionMode: "sequential" }),
    artifact_create: contract("artifact_create", "Create Artifact", "Store supplied UTF-8 text as a fixed Artifact and return its references. Use for authored analysis or reports; collect raw Job outputs with job_collect. Created text does not prove execution.", Type.Unsafe(shared.tools.artifact_create), { executionMode: "sequential" }),
    artifact_read: contract("artifact_read", "Read Artifact", "Read bounded Artifact content and metadata by exact artifact_id. Paging uses bytes and returns next_offset. A file path, Job ID or collection receipt is not an Artifact ID. Reading creates no evidence dependency.", Type.Unsafe(shared.tools.artifact_read), { executionMode: "sequential" }),

  };
  if (Object.keys(contracts).length !== PUBLIC_TOOL_NAMES.length
      || Object.keys(shared.tools).length !== PUBLIC_TOOL_NAMES.length
      || PUBLIC_TOOL_NAMES.some(name => contracts[name]?.name !== name || !Object.hasOwn(shared.tools, name))) {
    throw new Error("model tool inventory does not match its canonical schemas");
  }
  return Object.freeze(Object.fromEntries(Object.entries(contracts).map(
    ([key, value]) => [key, Object.freeze(value)],
  )));
}

function contract(key, label, description, parameters, extra = {}) {
  const metadata = PUBLIC_TOOL_METADATA[key];
  if (!metadata) throw new Error(`missing Harness metadata for ${key}`);
  return {
    name: key,
    label,
    description,
    parameters,
    metadata,
    ...extra,
  };
}
