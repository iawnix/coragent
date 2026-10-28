/** JSONL subprocess transport: no Host, Pi, or domain dependencies. */
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { packageRoot } from "../platform/resources.mjs";
import { KernelBridgeError, require_method } from "./ports.mjs";

const REPOSITORY_ROOT = packageRoot;
const ACTIVE_KERNEL_CHILDREN = new Set();
process.once("exit", () => {
  for (const child of ACTIVE_KERNEL_CHILDREN) child.kill();
});

/**
 * Create a persistent JSONL subprocess transport.
 *
 * `command` is executed directly with `shell: false`; callers can pin a
 * Python executable and environment instead of inheriting a shell lookup.
 */
export function create_jsonl_subprocess_transport({
  command = process.env.CORAGENT_PYTHON || "python3",
  args = [],
  cwd = REPOSITORY_ROOT,
  env = process.env,
  timeout_ms = null,
  max_pending = 256,
  coalesce = false,
} = {}) {
  if (typeof command !== "string" || command.length === 0) throw new TypeError("subprocess command is required");
  if (!Array.isArray(args) || args.some((item) => typeof item !== "string")) {
    throw new TypeError("subprocess args must be an array of strings");
  }
  if (timeout_ms !== null && (!Number.isSafeInteger(timeout_ms) || timeout_ms <= 0 || timeout_ms > 2147483647))
    throw new TypeError("timeout_ms must be null or an integer between 1 and 2147483647");
  if (!Number.isInteger(max_pending) || max_pending <= 0) throw new TypeError("max_pending must be positive");

  const child = spawn(command, [...args, "-u", "-m", "research_agent.application.bridge_worker"], {
    cwd: resolve(cwd),
    env: { ...env },
    shell: false,
    stdio: ["pipe", "pipe", "pipe"],
  });
  let buffer = "";
  let stderr = "";
  let closed = false;
  let sequence = 0;
  const pending = new Map();
  const requests = new Map();
  ACTIVE_KERNEL_CHILDREN.add(child);
  const exited = new Promise(done => child.once("close", done));
  let closePromise;

  function fail_all(error) {
    if (closed) return;
    closed = true;
    for (const entry of pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(error);
    }
    pending.clear();
    requests.clear();
  }

  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (!line.trim()) continue;
      let response;
      try {
        response = JSON.parse(line);
      } catch (error) {
        fail_all(new KernelBridgeError("invalid JSONL response from Python runtime", { code: "invalid_kernel_response", cause: error }));
        return;
      }
      const entry = pending.get(response?.id);
      if (!entry) continue;
      pending.delete(response.id);
      requests.delete(entry.key);
      clearTimeout(entry.timer);
      if (response.ok === true) entry.resolve(response.result);
      else entry.reject(new KernelBridgeError(response?.error?.message || "Python runtime request failed", {
        code: response?.error?.code || "python_kernel_error",
        details: response?.error?.details || {},
      }));
    }
  });
  child.stderr.on("data", (chunk) => {
    stderr = `${stderr}${chunk}`.slice(-8192);
  });
  child.once("error", (error) => {
    ACTIVE_KERNEL_CHILDREN.delete(child);
    fail_all(new KernelBridgeError(`Python runtime process failed: ${error.message}`, { code: "kernel_process_error", cause: error }));
  });
  child.once("exit", (code, signal) => {
    ACTIVE_KERNEL_CHILDREN.delete(child);
    if (!closed) fail_all(new KernelBridgeError(`Python runtime process exited (${code ?? "signal"} ${signal || ""})${stderr ? `: ${stderr.trim()}` : ""}`, { code: "kernel_process_exit" }));
  });

  async function request(method, payload = {}) {
    if (!["workspace_files", "workspace_catalog", "workspace_initialize", "workspace_attach", "workspace_admit"].includes(method)) require_method(method);
    if (closed) throw new KernelBridgeError("Python runtime transport is closed", { code: "transport_closed" });
    const key = coalesce ? JSON.stringify([method, payload]) : null;
    if (key !== null && requests.has(key)) return requests.get(key);
    if (pending.size >= max_pending) throw new KernelBridgeError("Python runtime request capacity reached", {
      code: "kernel_request_busy", details: { command: payload.command, pending_requests: pending.size },
    });
    const id = `bridge_${++sequence}`;
    const message = `${JSON.stringify({ id, method, payload })}\n`;
    const started = Date.now();
    const promise = new Promise((resolve_result, reject) => {
      const timer = timeout_ms === null ? undefined : setTimeout(() => {
        // A timeout ends the caller's wait, not the Python operation. Keep its
        // capacity and coalescing entry until the actual reply or process exit.
        // Repeated refreshes cannot keep adding work behind a blocked request.
        reject(new KernelBridgeError(`Stopped waiting for Python runtime: ${payload.command || method}; the operation may still complete. Inspect its receipt before resubmitting.`, {
          code: "kernel_request_timeout", details: { request_id: id, command: payload.command || method,
            operation_request_id: payload.params?.request_id ?? payload.request_id ?? null,
            operation_state: "pending", action_outcome: "unknown", retry_safe: false,
            recovery: "The operation was not cancelled. Read the existing Job or transaction receipt using its original identity; do not submit a new action to compensate for this wait timeout.",
            elapsed_ms: Date.now() - started, pending_requests: pending.size,
            outstanding: [...pending].map(([request_id, entry]) => ({ request_id, command: entry.command,
              elapsed_ms: Date.now() - entry.started })) },
        }));
      }, timeout_ms);
      pending.set(id, { resolve: resolve_result, reject, timer, key, started, command: payload.command || method });
      child.stdin.write(message, (error) => {
        if (!error) return;
        clearTimeout(timer);
        pending.delete(id);
        requests.delete(key);
        reject(new KernelBridgeError(`cannot write Python runtime request: ${error.message}`, { code: "kernel_request_write_error", cause: error }));
      });
    });
    if (key !== null) requests.set(key, promise);
    return promise;
  }

  function close() {
    if (closePromise) return closePromise;
    closePromise = (async () => {
      fail_all(new KernelBridgeError("Python runtime transport closed", { code: "transport_closed" }));
      child.stdin.end();
      if (child.exitCode === null && child.signalCode === null) child.kill();
      const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
      try { await exited; }
      finally { clearTimeout(timer); ACTIVE_KERNEL_CHILDREN.delete(child); }
    })();
    return closePromise;
  }

  return Object.freeze({ request, close });
}
