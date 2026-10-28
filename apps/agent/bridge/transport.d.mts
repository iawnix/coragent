export interface KernelBridgeTransport {
  request(method: string, payload: Record<string, unknown>): Promise<Record<string, unknown>>;
  close?(): Promise<void> | void;
}

export interface JsonlSubprocessTransportOptions {
  readonly command?: string;
  readonly args?: readonly string[];
  readonly cwd?: string;
  readonly env?: NodeJS.ProcessEnv;
  /** null waits for the operation receipt; a number bounds only caller waiting. */
  readonly timeout_ms?: number | null;
  readonly max_pending?: number;
  readonly coalesce?: boolean;
}

export function create_jsonl_subprocess_transport(
  options?: JsonlSubprocessTransportOptions,
): KernelBridgeTransport;
