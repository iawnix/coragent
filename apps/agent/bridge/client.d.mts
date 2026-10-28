import type { KernelBridgeTransport } from "./transport.mjs";
import type { CommandId, CommandResults } from "../tools/commands.mjs";
export interface RuntimeBridge {
  readonly protocol_version: "kernel_bridge_port_2";
  readonly workspace_root: string;
  execute_command<C extends CommandId>(command: C, params?: Record<string, unknown>): Promise<CommandResults[C]>;
  transaction_get(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_recover(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_begin(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_prepare(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_commit(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_abort(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  transaction_commit_files(request?: Record<string, unknown>): Promise<Record<string, unknown>>;
  close(): Promise<void>;
}

export function create_runtime_bridge(request: {
  readonly workspace_root: string;
  readonly workspace_id?: string;
  readonly transport: KernelBridgeTransport;
}): RuntimeBridge;

export interface PythonRuntimeBridgeOptions {
  readonly workspace_root: string;
  readonly workspace_id?: string;
  readonly command?: string;
  readonly args?: readonly string[];
  readonly cwd?: string;
  readonly env?: NodeJS.ProcessEnv;
  /** Execution defaults to null; local queries default to 30000 milliseconds. */
  readonly timeout_ms?: number | null;
  readonly max_pending?: number;
  readonly coalesce?: boolean;
}
export function create_python_runtime_bridge(request: PythonRuntimeBridgeOptions): RuntimeBridge;

export interface QueryRuntimeBridge {
  execute_command<C extends 'research_read' | 'research_search' | 'job_list' | 'job_manager_assess'>(command: C, params?: Record<string, unknown>): Promise<CommandResults[C]>;
  close(): Promise<void>;
}
export function create_query_runtime_bridge(request: PythonRuntimeBridgeOptions): QueryRuntimeBridge;
