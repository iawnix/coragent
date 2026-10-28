import { MONITOR_SERVICE_ID } from "../contracts/monitor.mjs";
import { JOB_ADMISSION_SERVICE_ID } from "./admission/jobs.mjs";
import { SESSION_ADMISSION_SERVICE_ID } from "./admission/session.mjs";
import { CLIENT_QUERIES_SERVICE_ID } from "./services/queries.mjs";
import { createSessionCatalog } from "./session-catalog.mjs";
import { startSessionWorker } from "./worker-process.mjs";
import { realpath, mkdir, open, lstat } from "node:fs/promises";
import { createWorkspaceCatalog } from "../host/workspaces.mjs";
import { randomBytes } from "node:crypto";
import { join, resolve } from "node:path";
import { sessionActivityAt } from "../host/session-selection.mjs";

const INPUT_SERVICE = "coragent.input-admission";

/** CoRAgent owns processes and session discovery; Pi Durable owns execution and storage. */
export async function createCoRAgentHarnessBackend(options = {}) {
  const sourceRoot = absolute(options.sourceRoot || process.env.CORAGENT_PI_RUNTIME_ROOT, "sourceRoot");
  const packageRoot = await realpath(absolute(options.packageRoot || process.env.CORAGENT_PACKAGE_ROOT, "packageRoot"));
  const workspaceRoot = absolute(options.workspaceRoot, "workspaceRoot");
  const serverDirectory = absolute(options.serverDirectory, "serverDirectory");
  const sessionDir = absolute(options.sessionDir, "sessionDir");
  const stateRoot = absolute(options.stateRoot || join(serverDirectory, ".."), "stateRoot");
  const producerToken = await internalProducerToken(stateRoot);
  const workspaceCatalog = options.workspaceCatalog || createWorkspaceCatalog(workspaceRoot);
  const catalog = createSessionCatalog(sessionDir);
  const summaries = new Map((await catalog.list()).map(item => [`${item.workspaceId}/${item.id}`, item]));
  const bindings = new Map(), pending = new Map(), restarts = new Map(), removals = new Map();
  const timers = new Set();
  const serverId = options.serverId || "local";
  let socketPath = options.socketPath || join(serverDirectory, `${serverId}.sock`);
  let eventHandler = () => {}, closed = false;
  const recoveryHealth = { state: "recovering", recovered: 0, failures: [] };
  const workspace = async (id, extra = {}) => (await workspaceCatalog.resolve(id, extra)).source_root;
  const clientDescriptor = sessionId => ({ transport: "unix", server_id: serverId,
    socket_path: socketPath, server_directory: serverDirectory, session_id: sessionId });
  function summaryFor(summary, binding) {
    const raw = binding?.snapshot || normalizeLane(null);
    const created = new Date(summary.createdAt).toISOString();
    return { workspace_id: summary.workspaceId, session_id: summary.id, cwd: summary.cwd,
      online: Boolean(binding && !binding.worker.isClosed()), is_streaming: Boolean(raw.operation),
      turn_id: raw.operation?.operationId || null, name: null, created_at: created,
      updated_at: sessionActivityAt(summary.createdAt, raw), model: normalizeModelIdentity(raw.configuration?.model),
      client: binding ? clientDescriptor(summary.id) : null };
  }
  function findSummary(workspaceId, sessionId) {
    const summary = summaries.get(`${workspaceId}/${sessionId}`);
    if (!summary) throw error("session_not_found", "Session is not present in this workspace");
    return summary;
  }
  function publish(binding) {
    if (closed || binding.closed || removals.has(binding.key)) return;
    eventHandler({ workspace_id: binding.summary.workspaceId, session_id: binding.summary.id,
      session: summaryFor(binding.summary, binding), snapshot: hostSnapshot(binding.snapshot), view: binding.view, event: null });
  }
  async function serviceCall(binding, service, method, args) {
    return binding.worker.request("service", { service, method, ...(args === undefined ? {} : { args }) });
  }
  async function refreshOutcome(binding) {
    const sequence = binding.sequence;
    const response = await serviceCall(binding, INPUT_SERVICE, "latest");
    if (response.error) throw error(response.error.code, response.error.message);
    if (!binding.closed && sequence === binding.sequence) binding.snapshot = { ...binding.snapshot,
      lastResult: submissionOutcome(response.result),
      faulted: response.result?.status === "unanswered" && response.result?.reason === "faulted" };
  }
  function restart(binding) {
    if (closed || binding.closed) return;
    binding.closed = true; bindings.delete(binding.key);
    const attempt = (restarts.get(binding.key) || 0) + 1;
    restarts.set(binding.key, attempt);
    if (attempt > 5) {
      recoveryHealth.state = "degraded";
      recoveryHealth.failures.push({ workspace_id: binding.summary.workspaceId, session_id: binding.summary.id,
        code: "worker_restart_limit", message: "Session worker failed repeatedly; reopen the session to retry" });
      return;
    }
    const timer = setTimeout(() => {
      timers.delete(timer);
      if (closed || removals.has(binding.key) || !summaries.has(binding.key)) return;
      void openBinding(binding.summary.workspaceId, binding.summary.id).catch(cause => {
        recoveryHealth.state = "degraded";
        recoveryHealth.failures.push({ workspace_id: binding.summary.workspaceId, session_id: binding.summary.id,
          code: cause.code || "worker_restart_failed", message: cause.message });
      });
    }, Math.min(5000, 250 * 2 ** (attempt - 1)));
    timers.add(timer);
  }
  async function openBinding(workspaceId, sessionId, model) {
    const key = `${workspaceId}/${sessionId}`;
    if (closed) throw error("backend_closed", "Harness backend is closed");
    if (removals.has(key)) throw error("session_removing", "Session is being removed");
    if (bindings.get(key) && !bindings.get(key).worker.isClosed()) return bindings.get(key);
    if (pending.has(key)) return pending.get(key);
    const opening = (async () => {
      const root = await workspace(workspaceId, { attach: true });
      const summary = findSummary(workspaceId, sessionId);
      if (await realpath(summary.cwd) !== await realpath(root)) throw error("workspace_mismatch", "Session directory does not match its workspace");
      const binding = { key, summary, snapshot: normalizeLane(null), sequence: 0, closed: false, view: null };
      const update = view => {
        if (binding.closed || closed) return;
        binding.snapshot = normalizeLane(view, binding.view, binding.snapshot); binding.view = view; binding.sequence++;
        publish(binding);
        if (!view.docs["pi.live"]?.run) void refreshOutcome(binding).then(() => publish(binding)).catch(() => {});
      };
      binding.worker = startSessionWorker({ sourceRoot, packageRoot, metadata: summary, producerToken,
        model: model || options.model, onView: update, onExit: () => restart(binding) });
      try {
        const view = await binding.worker.startup;
        if (closed) throw error("backend_closed", "Harness backend is closed");
        if (binding.worker.isClosed()) throw error("worker_unavailable", "Session worker exited during startup");
        bindings.set(key, binding); update(view);
        const stable = setTimeout(() => { timers.delete(stable); if (!binding.closed) restarts.delete(key); }, 60_000);
        stable.unref(); timers.add(stable);
        return binding;
      } catch (cause) { binding.closed = true; await binding.worker.close(); throw cause; }
    })();
    pending.set(key, opening);
    try { return await opening; } finally { pending.delete(key); }
  }
  async function inputStatus(binding, requestId) {
    const response = await serviceCall(binding, INPUT_SERVICE, "status", { requestId });
    if (response.error) throw error(response.error.code, response.error.message);
    return submissionReceipt(response.result, requestId);
  }
  async function applyModel(binding, model) {
    if (model) await binding.worker.request("model/select", model);
  }
  async function resultFor(binding) {
    binding.view = await binding.worker.request("snapshot");
    binding.snapshot = normalizeLane(binding.view); binding.sequence++;
    await refreshOutcome(binding);
    return { session: summaryFor(binding.summary, binding), snapshot: hostSnapshot(binding.snapshot),
      client: clientDescriptor(binding.summary.id) };
  }
  const recovery = recoverSessionCatalog({ sessions: [...summaries.values()], workspaceCatalog,
    openSession: summary => openBinding(summary.workspaceId, summary.id), isClosed: () => closed,
  }).then(result => Object.assign(recoveryHealth, result));
  return {
    workspaceCatalog, serverId,
    get socketPath() { return socketPath; },
    setHostSocket(path) { socketPath = path; },
    setEventHandler(handler) { eventHandler = handler; },
    async listSessions(workspaceId) {
      await recovery; await workspace(workspaceId);
      return [...summaries.values()].filter(item => item.workspaceId === workspaceId)
        .map(item => summaryFor(item, bindings.get(`${workspaceId}/${item.id}`)))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    },
    async readSession(workspaceId, sessionId) { return resultFor(await openBinding(workspaceId, sessionId)); },
    async readView(workspaceId, sessionId) {
      const binding = await openBinding(workspaceId, sessionId);
      return { ...binding.view, failure: hostSnapshot(binding.snapshot).runtime_error };
    },
    async createSession({ workspace_id: workspaceId, session_id: sessionId, model }) {
      const cwd = await workspace(workspaceId);
      const summary = await catalog.create({ workspaceId, sessionId, cwd });
      summaries.set(`${workspaceId}/${summary.id}`, summary);
      return resultFor(await openBinding(workspaceId, summary.id, model));
    },
    async resumeSession({ workspace_id: workspaceId, session_id: sessionId, model }) {
      restarts.delete(`${workspaceId}/${sessionId}`);
      const binding = await openBinding(workspaceId, sessionId);
      await applyModel(binding, model); return resultFor(binding);
    },
    async removeSession(workspaceId, sessionId) {
      const key = `${workspaceId}/${sessionId}`;
      if (removals.has(key)) return removals.get(key);
      const removing = (async () => {
        await workspace(workspaceId, { attach: true }); findSummary(workspaceId, sessionId);
        await pending.get(key)?.catch(() => {});
        const binding = bindings.get(key);
        if (binding) { binding.closed = true; await binding.worker.close(); bindings.delete(key); }
        await catalog.remove(workspaceId, sessionId); summaries.delete(key); restarts.delete(key);
        return { accepted: true, recoverable: false };
      })();
      removals.set(key, removing);
      try { return await removing; } finally { removals.delete(key); }
    },
    async sendInput(params) {
      const binding = await openBinding(params.workspace_id, params.session_id);
      const requestId = params.client_message_id;
      if (params.source === "job_manager") {
        const response = await serviceCall(binding, JOB_ADMISSION_SERVICE_ID, "admit", {
          requestId, eventIds: params.event_ids, mode: params.mode, token: producerToken });
        if (!response.accepted || response.skipped) return { ...response, client_message_id: requestId,
          state: response.skipped ? "completed" : "rejected" };
        return { ...await inputStatus(binding, requestId), pending: response.pending === true, consumed: response.consumed === true };
      }
      const whenBusy = { auto: "followUp", follow_up: "followUp", steer: "steer" }[params.mode || "auto"];
      if (!whenBusy) throw error("invalid_input", "Unsupported input mode");
      const response = await serviceCall(binding, INPUT_SERVICE, "submit", { requestId, content: params.text, whenBusy });
      if (response.error) return { client_message_id: requestId, state: "rejected", accepted: false, error: response.error };
      return inputStatus(binding, requestId);
    },
    async inputStatus(params) { return inputStatus(await openBinding(params.workspace_id, params.session_id), params.client_message_id); },
    async monitor(method, params) {
      const response = await serviceCall(await openBinding(params.workspace_id, params.session_id), MONITOR_SERVICE_ID, "handle", { method, params });
      if (response.error) throw error(response.error.code, response.error.message);
      return method === "monitor/health" ? { ...response.result, recovery: structuredClone(recoveryHealth) } : response.result;
    },
    async interrupt(params) { return serviceCall(await openBinding(params.workspace_id, params.session_id),
      SESSION_ADMISSION_SERVICE_ID, "interrupt", { turnId: params.turn_id }); },
    async models(params) {
      const result = await (await openBinding(params.workspace_id, params.session_id)).worker.request("models/list");
      return { ...result, selected: normalizeModelIdentity(result.selected) };
    },
    async selectModel(params) {
      await applyModel(await openBinding(params.workspace_id, params.session_id), params.model);
      return { accepted: true, model: params.model };
    },
    async query(params) {
      const binding = await openBinding(params.workspace_id, params.session_id);
      if (params.query === "view") {
        const result = await resultFor(binding);
        return { ...binding.view, failure: result.snapshot.runtime_error };
      }
      if (params.query === "compaction") return binding.worker.request("compaction/status", { task_id: params.args });
      if (params.query === "runtime") return binding.worker.request("runtime/status");
      if (!["telemetry", "research", "systemPrompt"].includes(params.query)) throw error("invalid_query", "Unsupported session query");
      return serviceCall(binding, CLIENT_QUERIES_SERVICE_ID, params.query, params.args);
    },
    async compact(params) { return (await openBinding(params.workspace_id, params.session_id)).worker.request("compact", { instructions: params.instructions }); },
    async configure(params) { return (await openBinding(params.workspace_id, params.session_id)).worker.request("configure", { thinkingLevel: params.thinking_level }); },
    async reload(params) { return (await openBinding(params.workspace_id, params.session_id)).worker.request("reload"); },
    async pause(params) { return (await openBinding(params.workspace_id, params.session_id)).worker.request("abort"); },
    async retry(params) { return (await openBinding(params.workspace_id, params.session_id)).worker.request("runtime/retry", { task_id: params.task_id }); },
    async close() {
      if (closed) return;
      closed = true;
      for (const timer of timers) clearTimeout(timer);
      await Promise.allSettled([...pending.values()]);
      await Promise.allSettled([...removals.values()]);
      await Promise.allSettled([...bindings.values()].map(async binding => { binding.closed = true; await binding.worker.close(); }));
      bindings.clear();
      if (!options.workspaceCatalog) await workspaceCatalog.close();
    },
  };
}

/** Recover only sessions owned by the current workspace catalog. */
export async function recoverSessionCatalog({ sessions, workspaceCatalog, openSession, isClosed }) {
  const workspaces = new Set((await workspaceCatalog.list()).map(row => row.workspace_id));
  const selected = sessions.filter(summary => workspaces.has(summary.workspaceId));
  const result = { state: "recovering", recovered: 0, failures: [] };
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(4, selected.length) }, async () => {
    while (!isClosed() && next < selected.length) {
      const summary = selected[next++];
      try {
        await openSession(summary);
        result.recovered += 1;
      } catch (cause) {
        result.failures.push({ workspace_id: summary.workspaceId, session_id: summary.sessionId,
          code: cause.code || "session_recovery_failed", message: cause.message });
      }
    }
  }));
  result.state = isClosed() ? "stopped" : result.failures.length ? "degraded" : "ready";
  return result;
}

export function submissionReceipt(record, requestId) {
  if (!record) return { client_message_id: requestId, state: "not_found", accepted: false };
  const state = { queued: "queued", placed: "running", done: "completed", unanswered: "failed" }[record.status];
  if (!state || record.type !== "input") throw error("invalid_submission", "Pi returned an invalid input submission");
  return { client_message_id: requestId, operation_id: String(record.id), accepted: true, state,
    submission: record,
    ...(record.status === "queued" ? { entry_id: String(record.id) } : {}),
    ...(record.status === "unanswered" ? { error: { code: record.reason,
      message: typeof record.detail === "string" ? record.detail : record.reason } } : {}),
  };
}

function submissionOutcome(record) {
  if (!record || !["done", "unanswered"].includes(record.status)) return null;
  return { operationId: String(record.id), status: record.status === "done" ? "completed" : "failed",
    ...(record.status === "unanswered" ? { error: { code: record.reason,
      message: typeof record.detail === "string" ? record.detail : record.reason } } : {}),
  };
}

function hostSnapshot(value) {
  const raw = normalizeLane(value);
  const operation = raw.operation || null;
  const queues = Array.isArray(raw.queues) ? raw.queues : [];
  const transcript = raw.transcript;
  const failure = operation === null ? normalizeOperationFailure(raw.lastResult) : null;
  return {
    messages: appendFailureMessage(transcript, failure),
    online: true,
    can_prompt: true,
    is_streaming: operation !== null,
    turn_id: operation?.operationId || operation?.id || null,
    operation: operation === null ? null : {
      id: operation.id || operation.operationId || null,
      kind: operation.kind || "run",
      status: operation.status || "open",
      started_at: operation.startedAt || null,
      retry: operation.retry || null,
      deferred: operation.deferred || null,
    },
    pending_messages: queues.length > 0,
    queues,
    streaming_message: operation?.streamingMessage || null,
    running_tools: Array.isArray(operation?.runningTools) ? operation.runningTools : [],
    last_result: raw.lastResult || null,
    runtime_error: failure,
    faulted: raw.faulted,
    model: normalizeModelIdentity(raw.configuration?.model),
  };
}

/** Project the pinned Pi ConversationView for Host presentation. */
function normalizeLane(value, previousView, previousLane) {
  const source = value || { entries: [], docs: {} };
  if (source.__coragentLane === true) return source;
  const docs = source.docs && typeof source.docs === "object" ? source.docs : {};
  const agent = docs["pi.agent"] && typeof docs["pi.agent"] === "object" ? docs["pi.agent"] : {};
  const live = docs["pi.live"] && typeof docs["pi.live"] === "object" ? docs["pi.live"] : {};
  const inbox = docs["pi.inbox"] && typeof docs["pi.inbox"] === "object" ? docs["pi.inbox"] : {};
  const run = live.run && typeof live.run === "object" ? live.run : null;
  const generation = live.generation && typeof live.generation === "object" ? live.generation : null;
  const inputs = Array.isArray(run?.inputs) ? run.inputs : [];
  const submissionId = inputs.length > 0 ? String(inputs[0]) : null;
  if (run && !submissionId) throw error("invalid_pi_view", "Pi run has no input submission identity");
  const operation = run ? {
    // `id` remains the Pi scheduler task identity for diagnostics. CoRAgent's
    // public operation/turn identity is the admitted submission ID returned
    // by input admission.
    id: String(run.taskId),
    taskId: String(run.taskId),
    operationId: submissionId,
    inputs: inputs.map(String),
    kind: "run",
    status: generation?.retry || generation?.deferred ? "suspended" : "running",
    retry: generation?.retry || null,
    deferred: generation?.deferred || null,
    streamingMessage: generation?.message || null,
    runningTools: Array.isArray(live.tools) ? live.tools.filter((tool) => tool?.status === "running") : [],
  } : null;
  const queues = Array.isArray(inbox.items) ? inbox.items.map((item) => ({
    entryId: String(item.id),
    id: String(item.id),
    mode: item.mode,
    message: item.content ?? item.entry ?? null,
  })) : [];
  if (!Array.isArray(source.entries) || !source.docs) throw error("invalid_pi_view", "Expected pinned Pi ConversationView");
  const transcript = source.entries === previousView?.entries && previousLane ? previousLane.transcript
    : source.entries.flatMap(entry => (entry.model || []).map(message => ({ ...message, entry_id: entry.id })));
  return {
    __coragentLane: true,
    operation,
    queues,
    transcript,
    lastResult: null,
    faulted: null,
    configuration: { model: agent.model || null },
  };
}

function appendFailureMessage(transcript, failure) {
  if (!failure) return transcript;
  const messages = transcript.slice();
  const failedIndex = messages.findLastIndex(message => message?.role === "assistant" && message?.outputState === "failed");
  if (failedIndex >= 0) {
    const entry = messages[failedIndex];
    messages[failedIndex] = { ...entry, failure };
    return messages;
  }
  messages.push({
    role: "assistant",
    content: [],
    outputState: "failed",
    failure,
  });
  return messages;
}

export function normalizeOperationFailure(result) {
  if (!result || typeof result !== "object") return null;
  const source = result.error && typeof result.error === "object" ? result.error : result;
  if (result.status !== "failed" && !result.error) return null;
  const message = typeof source.message === "string" && source.message.trim()
    ? source.message.trim()
    : "Pi operation failed";
  const operationId = typeof result.operationId === "string"
    ? result.operationId
    : null;
  const statusCode = Number.isSafeInteger(source.statusCode)
    ? source.statusCode
    : Number.isSafeInteger(source.status)
      ? source.status
      : numericHttpStatus(message);
  return {
    code: typeof source.code === "string" && source.code.trim() ? source.code.trim().slice(0, 96) : "operation_failed",
    summary: failureSummary(source.code, statusCode),
    detail: message.slice(0, 4000),
    ...(statusCode === null ? {} : { statusCode }),
    retryable: source.retryable === true || result.retryable === true,
    ...(operationId ? { operationId } : {}),
  };
}

function numericHttpStatus(message) {
  const match = String(message).match(/(?:^|\s)([1-5][0-9]{2})(?=\s|:|$)/);
  return match ? Number(match[1]) : null;
}

export function failureSummary(code, statusCode = null) {
  switch (code) {
    case "provider_error":
      return "模型服务拒绝了请求";
    case "provider_auth_failed":
      return "模型服务认证失败";
    case "provider_unavailable":
      return "模型服务暂时不可用";
    case "provider_rate_limited":
      return "模型服务限制了请求频率";
    case "auth_unavailable":
      return "模型服务认证不可用";
    case "server_error":
    case "upstream_server_error":
      return "模型服务发生服务器错误";
    default:
      if (statusCode !== null && statusCode >= 500 && statusCode < 600) return "模型服务暂时不可用";
      return "程序未能完成本次回复";
  }
}

function normalizeModelIdentity(value) {
  if (!value || typeof value !== "object" || typeof value.provider !== "string") return null;
  const id = value.modelId;
  return typeof id === "string" ? { provider: value.provider, id } : null;
}

function absolute(value, label) {
  if (typeof value !== "string" || !value.startsWith("/")) throw new TypeError(`${label} must be absolute`);
  return resolve(value);
}

async function internalProducerToken(stateRoot) {
  await mkdir(stateRoot, { recursive: true, mode: 0o700 });
  const path = join(stateRoot, "internal-producer.key");
  let handle;
  try {
    handle = await open(path, "wx", 0o600);
    const token = randomBytes(32).toString("hex");
    await handle.writeFile(token); await handle.sync();
    return token;
  } catch (cause) {
    if (cause.code !== "EEXIST") throw cause;
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink() || (info.mode & 0o077)) throw error("invalid_producer_identity", "Internal producer identity must be a private regular file");
    const existing = await open(path, "r");
    try {
      const token = await existing.readFile("utf8");
      if (!/^[a-f0-9]{64}$/u.test(token)) throw error("invalid_producer_identity", "Invalid internal producer identity");
      return token;
    } finally { await existing.close(); }
  } finally { await handle?.close(); }
}

function error(code, message, retryable = false, cause) {
  const value = new Error(message, cause ? { cause } : undefined);
  value.code = code;
  value.retryable = retryable;
  return value;
}
