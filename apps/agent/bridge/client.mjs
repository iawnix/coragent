import { resolve } from "node:path";
import { require_workspace_id } from "../contracts/workspace-id.mjs";
import { KERNEL_BRIDGE_PORT_VERSION, KernelBridgeError, require_method } from "./ports.mjs";
import { create_jsonl_subprocess_transport } from "./transport.mjs";

function require_workspace_root(value) {
  if (typeof value !== "string" || value.length === 0) throw new TypeError("workspace_root is required");
  return resolve(value);
}

function require_object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${label} must be an object`);
  }
  return value;
}

function require_transport(transport) {
  if (!transport || typeof transport.request !== "function") {
    throw new TypeError("kernel bridge transport requires request(method, payload)");
  }
  return transport;
}

function ensure_result(value, method) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new KernelBridgeError(`Python runtime returned a non-object result for ${method}`, {
      code: "invalid_kernel_result",
    });
  }
  return value;
}

/**
 * Build a runtime bridge over any async request transport.
 *
 * The transport receives `(method, payload)` where payload always contains
 * the immutable bridge workspace_root. It may return a Promise for a JSON
 * object or throw a KernelBridgeError.
 */
export function create_runtime_bridge({ workspace_root, workspace_id, transport } = {}) {
  const root = require_workspace_root(workspace_root);
  if (workspace_id !== undefined) require_workspace_id(workspace_id);
  const channel = require_transport(transport);

  async function invoke(method, request = {}) {
    require_method(method);
    require_object(request, `${method} request`);
    const supplied_root = request.workspace_root ?? request.root;
    if (supplied_root !== undefined && require_workspace_root(supplied_root) !== root) {
      throw new KernelBridgeError("research_workspace_root_mismatch", { code: "workspace_root_mismatch" });
    }
    const supplied_id = request.workspace_id;
    if (workspace_id !== undefined && supplied_id !== undefined && supplied_id !== workspace_id) {
      throw new KernelBridgeError("research_workspace_id_mismatch", { code: "workspace_id_mismatch" });
    }
    const payload = {
      ...request,
      workspace_root: root,
      ...(workspace_id === undefined ? {} : { workspace_id }),
    };
    try {
      return ensure_result(await channel.request(method, payload), method);
    } catch (error) {
      if (error instanceof KernelBridgeError) throw error;
      throw new KernelBridgeError(`Python runtime ${method} failed: ${error?.message || String(error)}`, {
        code: "kernel_request_failed",
        cause: error,
      });
    }
  }

  return Object.freeze({
    protocol_version: KERNEL_BRIDGE_PORT_VERSION,
    workspace_root: root,
    execute_command: (command, params = {}) => {
      if (typeof command !== "string" || command.length === 0) throw new TypeError("command is required");
      require_object(params, "command params");
      return invoke("execute_command", { command, params });
    },
    transaction_get: (request = {}) => invoke("transaction_get", request),
    transaction_recover: (request = {}) => invoke("transaction_recover", request),
    transaction_begin: (request = {}) => invoke("transaction_begin", request),
    transaction_prepare: (request = {}) => invoke("transaction_prepare", request),
    transaction_commit: (request = {}) => invoke("transaction_commit", request),
    transaction_abort: (request = {}) => invoke("transaction_abort", request),
    transaction_commit_files: (request = {}) => invoke("transaction_commit_files", request),
    close: async () => {
      if (typeof channel.close === "function") await channel.close();
    },
  });
}


/** Execution waits for its receipt. Scheduler, command and transfer deadlines
 * belong to the operation; a generic 30s timer cannot safely end a write. */
export function create_python_runtime_bridge({ workspace_root, workspace_id, timeout_ms = null, ...transport_options } = {}) {
  const transport = create_jsonl_subprocess_transport({ ...transport_options, timeout_ms });
  const bridge = create_runtime_bridge({ workspace_root, workspace_id, transport });
  return Object.freeze({ ...bridge });
}

// These commands read local durable state. In particular, job_status is not a
// local query: it may contact a scheduler and must stay on the execution bridge.
const LOCAL_QUERIES = new Set(["research_read", "research_search", "job_list", "job_manager_assess"]);

/** A bounded query process using the same protocol, commands and workspace locks. */
export function create_query_runtime_bridge({ timeout_ms = 30_000, ...options } = {}) {
  const bridge = create_python_runtime_bridge({ ...options, timeout_ms, max_pending: 16, coalesce: true });
  return Object.freeze({
    execute_command(command, params = {}) {
      if (!LOCAL_QUERIES.has(command)) throw new TypeError(`Not a local runtime query: ${command}`);
      return bridge.execute_command(command, params);
    },
    close: () => bridge.close(),
  });
}
