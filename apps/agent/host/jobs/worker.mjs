import { execFile } from "node:child_process";
import { createWorkspaceCatalog } from "../workspaces.mjs";
import { lstat, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { validate_workspace_manifest } from "../workspace.mjs";
import { createObservationScheduler, firstSessionBatches, interleaveWorkspaces, mapConcurrent } from "./scheduling.mjs";


const executeFile = promisify(execFile);
import { packageRoot } from "../../platform/resources.mjs";
const python = process.env.CORAGENT_PYTHON || "python3";
const OBSERVATION_TIMEOUT_SECONDS = 30;
const WORKER_CONCURRENCY = 4;

// Job Manager only wakes the owning Agent; notification decisions belong to email Skill.
export async function deliverJobEvent({ workspace, delivery, deliveries = [delivery], runJson, sendWake, onDelivered }) {
  const errors = [];
  const requestId = deliveries[0].request_id;
  let claim;
  let result = [];
  try {
    claim = await runJson("claim", workspace, ["--request-id", requestId, "--channel", "wake"]);
    if (!claim.claimed) return errors;
    const hostWorkspaceId = await jobHostWorkspaceId(workspace, claim.events[0]);
    if (claim.events.some(event => event.workspace_id !== hostWorkspaceId)) {
      throw new Error("monitor event belongs to another workspace");
    }
    if (!claim.session_id) throw new Error("monitor has no owning session; wake remains pending");
    // Admission and retries use the immutable batch identity from the claim.
    const response = await sendWake({ workspace_id: hostWorkspaceId, session_id: claim.session_id,
      request_id: claim.request_id, client_message_id: claim.request_id, source: "job_manager", mode: "next_run",
      event_ids: claim.batch_event_ids });
    if (response?.error?.code === "busy" || response?.pending === true) return errors;
    if (response?.accepted !== true || response?.state === "uncertain") {
      throw new Error(response?.error?.message || "Host returned an uncertain monitor wake");
    }
    result = ["--delivered"];
  } catch (error) {
    errors.push(`wake: ${errorMessage(error)}`);
    result = ["--error", errorMessage(error)];
  } finally {
    if (claim?.claimed) {
      await runJson("complete", workspace,
        ["--request-id", requestId, "--channel", "wake", "--claim-token", claim.claim_token, ...result]);
      if (result[0] === "--delivered") onDelivered?.();
    }
  }
  return errors;
}

export async function jobHostWorkspaceId(workspace, event) {
  // The canonical manifest identity is the same value used by the compute
  // plane and Host routes. The physical directory name is not an identity.
  const root = resolve(workspace);
  const manifestPath = join(root, "workspace_manifest.json");
  const [directory, identityStat] = await Promise.all([lstat(root), lstat(manifestPath).catch(() => null)]);
  if (!directory.isDirectory() || directory.isSymbolicLink() || await realpath(root) !== root
    || !identityStat?.isFile() || identityStat.isSymbolicLink()) throw new Error("monitor workspace must be a physical initialized directory");
  const identity = JSON.parse(await readFile(manifestPath, "utf8"));
  try {
    validate_workspace_manifest(identity, root);
  } catch (error) {
    throw new Error("monitor workspace identity is invalid", { cause: error });
  }
  if (identity.workspace_mode !== "research" || identity.state !== "ready") {
    throw new Error("monitor workspace identity is invalid");
  }
  if (event.workspace_id !== identity.workspace_id) throw new Error("monitor event belongs to another workspace");
  return identity.workspace_id;
}

export async function runJobWorker(options, signal) {
  const { connectHost } = await import("../../transport/host-client.mjs");
  const token = process.env.CORAGENT_INTERNAL_JOB_TOKEN;
  delete process.env.CORAGENT_INTERNAL_JOB_TOKEN;
  if (!token) throw new Error("Job Manager must be started by the installation Host");
  let connection;
  const catalog = createWorkspaceCatalog(options.workspaceRoot, { python });
  const sendWake = async (params) => {
    const pending = connection ??= connectHost({ socketPath: options.hostSocket });
    try {
      const client = await pending;
      if (signal.aborted) { client.close(); throw signal.reason; }
      return await client.request("internal/job-event", { ...params, token });
    } catch (error) {
      if (connection === pending) connection = undefined;
      void pending.then(client => client.close(), () => {});
      throw error;
    }
  };
  const closeConnection = () => { void connection?.then(client => client.close(), () => {}); };
  signal.addEventListener("abort", closeConnection, { once: true });
  const runJson = (command, workspace, extra, commandSignal = signal) => runJobManagerJson(command, workspace, extra, commandSignal);
  try {
    await runJobWorkerLoops(options, signal, { listWorkspaces: () => catalog.list(), runJson, sendWake,
      publishHealth: value => writeHealth(options.stateRoot, value) });
  } finally {
    signal.removeEventListener("abort", closeConnection);
    closeConnection();
    await catalog.close();
  }
}

/** Observation and delivery share durable records, but never await each other's work. */
export async function runJobWorkerLoops(options, signal, { listWorkspaces, runJson, sendWake, publishHealth }) {
  const controller = new AbortController();
  signal = AbortSignal.any([signal, controller.signal]);
  const executeJson = runJson;
  runJson = (command, workspace, extra = []) => executeJson(command, workspace, extra, signal);
  const health = { pid: process.pid, poll_interval_ms: options.intervalMs,
    last_successful_poll: null, last_successful_observation: null, last_successful_delivery: null,
    last_observation_error: null, last_delivery_error: null, last_error: null };
  const observationErrors = new Map();
  const deliveryErrors = new Map();
  let observationKeys = new Set();
  const observedSincePoll = new Set();
  let healthWrite = Promise.resolve();
  const recordErrors = (records, workspace, key, errors) => {
    const identity = JSON.stringify([workspace, key]);
    if (errors.length) records.set(identity, { workspace, key, message: errors.join("; ") });
    else records.delete(identity);
  };
  const messages = records => [...records.values()].map(row => row.message);
  const publish = () => {
    health.last_observation_error = messages(observationErrors).join("; ") || null;
    health.last_delivery_error = messages(deliveryErrors).join("; ") || null;
    health.last_error = [health.last_observation_error, health.last_delivery_error].filter(Boolean).join("; ") || null;
    const snapshot = { ...health, updated_at: new Date().toISOString() };
    // Both loops publish to one file; serialize its atomic rename.
    healthWrite = healthWrite.catch(() => {}).then(() => publishHealth(snapshot));
    return healthWrite;
  };
  const scheduler = createObservationScheduler({ signal, intervalMs: options.once ? Infinity : options.intervalMs,
    concurrency: WORKER_CONCURRENCY,
    observe: item => runJson("tick", item.workspace,
      ["--monitor-id", item.monitor_id, "--timeout-seconds", String(OBSERVATION_TIMEOUT_SECONDS)]),
    onResult(item, result, error) {
      if (signal.aborted) return;
      const errors = error ? [monitorCommandError(error)] : [
        ...(result.registration_errors || []), ...(result.monitors || []).map(row => row.error).filter(Boolean)];
      const key = JSON.stringify([item.workspace, item.monitor_id]);
      if (!observationKeys.has(key)) return;
      recordErrors(observationErrors, item.workspace, `monitor:${item.monitor_id}`, errors);
      if (!errors.length) {
        health.last_successful_observation = new Date().toISOString();
        observedSincePoll.add(key);
      } else observedSincePoll.delete(key);
      if (!observationErrors.size && [...observationKeys].every(identity => observedSincePoll.has(identity))) {
        health.last_successful_poll = health.last_successful_observation;
        observedSincePoll.clear();
      }
    },
  });
  const observeLoop = async () => {
    const inventory = new Map();
    do {
      try {
        const workspaces = await listWorkspaces();
        const roots = new Set(workspaces.map(row => row.source_root));
        for (const root of inventory.keys()) if (!roots.has(root)) inventory.delete(root);
        for (const [key, row] of observationErrors) if (row.workspace && !roots.has(row.workspace)) observationErrors.delete(key);
        recordErrors(observationErrors, null, "catalog", []);
        await mapConcurrent(workspaces, WORKER_CONCURRENCY, async ({ source_root: workspace }) => {
          if (signal.aborted) return;
          try {
            const result = await runJson("observations", workspace);
            inventory.set(workspace, result.observations.map(row => ({ ...row, workspace })));
            const monitors = new Set(result.observations.map(row => `monitor:${row.monitor_id}`));
            for (const [key, row] of observationErrors) {
              if (row.workspace === workspace && row.key.startsWith("monitor:") && !monitors.has(row.key)) observationErrors.delete(key);
            }
            recordErrors(observationErrors, workspace, "inventory", result.registration_errors || []);
          } catch (error) { recordErrors(observationErrors, workspace, "inventory", [monitorCommandError(error)]); }
        });
        const observations = [...inventory.values()].flat();
        observationKeys = new Set(observations.map(row => JSON.stringify([row.workspace, row.monitor_id])));
        for (const key of observedSincePoll) if (!observationKeys.has(key)) observedSincePoll.delete(key);
        scheduler.update(observations);
        if (!observationKeys.size && !observationErrors.size) health.last_successful_poll = new Date().toISOString();
        if (options.once) await scheduler.drain();
      } catch (error) { recordErrors(observationErrors, null, "catalog", [monitorCommandError(error)]); }
      if (!signal.aborted) await publish();
      if (options.once || signal.aborted) break;
      await delay(options.intervalMs, signal);
    } while (!signal.aborted);
  };
  const deliverOnce = async () => {
      try {
        const workspaces = await listWorkspaces();
        const roots = new Set(workspaces.map(row => row.source_root));
        for (const [key, row] of deliveryErrors) if (row.workspace && !roots.has(row.workspace)) deliveryErrors.delete(key);
        recordErrors(deliveryErrors, null, "catalog", []);
        const batches = (await mapConcurrent(workspaces, WORKER_CONCURRENCY, async ({ source_root: workspace }) => {
          if (signal.aborted) return [];
          try {
            const pending = await runJson("pending", workspace);
            recordErrors(deliveryErrors, workspace, "pending", []);
            const batches = firstSessionBatches(pending.deliveries || []);
            const sessions = new Set(batches.map(rows => `session:${rows[0].session_id}`));
            for (const [key, row] of deliveryErrors) {
              if (row.workspace === workspace && row.key.startsWith("session:") && !sessions.has(row.key)) deliveryErrors.delete(key);
            }
            return batches.map(deliveries => ({ workspace, deliveries }));
          } catch (error) {
            recordErrors(deliveryErrors, workspace, "pending", [monitorCommandError(error)]);
            return [];
          }
        })).flat();
        await mapConcurrent(interleaveWorkspaces(batches), WORKER_CONCURRENCY, async ({ workspace, deliveries }) => {
          if (signal.aborted) return;
          let errors;
          try {
            errors = await deliverJobEvent({ workspace, deliveries, runJson, sendWake,
              onDelivered() { health.last_successful_delivery = new Date().toISOString(); } });
          }
          catch (error) { errors = [monitorCommandError(error)]; }
          recordErrors(deliveryErrors, workspace, `session:${deliveries[0].session_id}`, errors);
        });
        await mapConcurrent(workspaces, WORKER_CONCURRENCY, async ({ source_root: workspace }) => {
          if (signal.aborted) return;
          const errors = [...observationErrors.values(), ...deliveryErrors.values()]
            .filter(row => row.workspace === workspace).map(row => row.message);
          try {
            await runJson("health", workspace, errors.length ? ["--error", errors.join("; ")] : []);
            recordErrors(deliveryErrors, workspace, "health", []);
          } catch (error) { recordErrors(deliveryErrors, workspace, "health", [monitorCommandError(error)]); }
        });
      } catch (error) { recordErrors(deliveryErrors, null, "catalog", [monitorCommandError(error)]); }
      if (!signal.aborted) await publish();
  };
  const deliveryLoop = async () => {
    do {
      await deliverOnce();
      if (options.once || signal.aborted) break;
      await delay(options.intervalMs, signal);
    } while (!signal.aborted);
  };
  const loops = [observeLoop(), deliveryLoop()].map(operation => operation.catch(error => { controller.abort(error); throw error; }));
  try {
    const results = await Promise.allSettled(loops);
    const failure = results.find(result => result.status === "rejected");
    if (failure) throw failure.reason;
    // Include events emitted after the concurrent delivery pass began.
    if (options.once && !signal.aborted) await deliverOnce();
  }
  finally { scheduler.stop(); await scheduler.drain(); await healthWrite; }
}

async function writeHealth(stateRoot, value) {
  if (!stateRoot) return;
  await mkdir(stateRoot, { recursive: true, mode: 0o700 });
  const temporary = join(stateRoot, `job-manager-health.${process.pid}.tmp`);
  await writeFile(temporary, `${JSON.stringify(value)}\n`, { mode: 0o600 });
  await rename(temporary, join(stateRoot, "job-manager-health.json"));
}

async function runJobManagerJson(command, workspace, extra = [], signal) {
  const operation = executeFile(python, [join(packageRoot, "apps/cli/job_manager.py"), command, "--root", workspace, ...extra], {
    cwd: workspace, env: { ...process.env, PYTHONNOUSERSITE: "1" }, maxBuffer: 8 * 1024 * 1024,
    timeout: command === "tick" ? (OBSERVATION_TIMEOUT_SECONDS + 5) * 1000 : 10_000, killSignal: "SIGTERM", signal });
  // AbortSignal rejects execFile before Python's SIGTERM cleanup has completed.
  const closed = new Promise(resolvePromise => operation.child.once("close", resolvePromise));
  let completed;
  try { completed = await operation; }
  finally { await closed; }
  const value = JSON.parse(completed.stdout.trim());
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`invalid monitor JSON for ${command}`);
  return value;
}
export function parseJobWorkerArguments(arguments_) {
  const values = { intervalMs: Number(process.env.CORAGENT_JOB_POLL_INTERVAL_MS || "5000"), once: false };
  const properties = { "workspace-root": "workspaceRoot", "host-socket": "hostSocket", "state-root": "stateRoot",
    "server-directory": "serverDirectory", "server-id": "serverId", "interval-ms": "intervalMs" };
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--once") { values.once = true; continue; }
    const match = /^--([^=]+)(?:=(.*))?$/u.exec(argument);
    const property = match && properties[match[1]];
    if (!property) throw new Error(`unknown monitor option: ${argument}`);
    const value = match[2] ?? arguments_[++index];
    if (!value || value.startsWith("--")) throw new Error(`${argument} requires one value`);
    values[property] = property === "intervalMs" ? Number(value) : value;
  }
  values.hostSocket ??= values.serverDirectory && values.serverId ? join(values.serverDirectory, `${values.serverId}.sock`) : undefined;
  values.stateRoot ??= values.serverDirectory;
  if (!values.workspaceRoot || !values.hostSocket) throw new Error("monitor requires --workspace-root and --host-socket");
  if (!Number.isInteger(values.intervalMs) || values.intervalMs < 250 || values.intervalMs > 86_400_000) throw new Error("monitor interval must be between 250 and 86400000 milliseconds");
  return values;
}
function delay(milliseconds, signal) {
  if (signal.aborted) return Promise.resolve();
  return new Promise((resolvePromise) => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolvePromise(); };
    const timer = setTimeout(finish, milliseconds);
    signal.addEventListener("abort", finish, { once: true });
  });
}
function monitorCommandError(error) {
  const output = String(error?.stderr || error?.stdout || "").trim();
  if (output) return output.slice(-4_000);
  return errorMessage(error);
}
function errorMessage(error) { return error instanceof Error ? error.message : String(error); }
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const controller = new AbortController();
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) process.once(signal, () => controller.abort());
  try { await runJobWorker(parseJobWorkerArguments(process.argv.slice(2)), controller.signal); }
  catch (error) { if (!controller.signal.aborted) { process.stderr.write(`CoRAgent Job Manager stopped: ${errorMessage(error)}\n`); process.exitCode = 1; } }
}
