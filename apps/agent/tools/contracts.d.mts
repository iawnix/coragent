import type { TSchema } from "typebox";
import type { ToolParameters } from "./parameters.mjs";

export type PublicToolKey = keyof ToolParameters;

export const PUBLIC_TOOL_NAMES: readonly PublicToolKey[];
export const PUBLIC_TOOL_EXECUTION: Readonly<Record<string, string>>;
export const PUBLIC_TOOL_METADATA: Readonly<Record<string, {
  readonly authority: string;
  readonly effect: string;
  readonly replay: string;
  readonly phase: string;
}>>;
export function validateHarnessToolDefinition(tool: any, options?: {
  source?: string;
  requireCanonical?: boolean;
}): any;

type ToolContract<P, N extends string = string> = {
  readonly name: N;
  readonly label: string;
  readonly description: string;
  readonly parameters: TSchema & { static: P };
  readonly metadata: Readonly<{
    readonly authority: string;
    readonly effect: string;
    readonly replay: string;
    readonly phase: string;
  }>;
  readonly promptSnippet?: string;
  readonly promptGuidelines?: readonly string[];
  readonly executionMode?: "sequential" | "parallel";
  readonly replay?: string;

};

export interface PublicToolContracts {
  readonly task_begin: ToolContract<ToolParameters["task_begin"]>;
  readonly task_read: ToolContract<ToolParameters["task_read"]>;
  readonly task_update: ToolContract<ToolParameters["task_update"]>;
  readonly research_read: ToolContract<ResearchReadToolParams>;
  readonly research_search: ToolContract<ToolParameters["research_search"]>;
  readonly research_create: ToolContract<ToolParameters["research_create"]>;
  readonly research_update: ToolContract<ToolParameters["research_update"]>;
  readonly research_result: ToolContract<ToolParameters["research_result"]>;
  readonly job_start: ToolContract<JobStartToolParams>;
  readonly job_status: ToolContract<JobStatusToolParams>;
  readonly job_collect: ToolContract<JobCollectToolParams>;
  readonly job_cancel: ToolContract<JobCancelToolParams>;
  readonly job_probe: ToolContract<JobProbeToolParams>;
  readonly job_reconcile: ToolContract<JobReconcileToolParams>;
  readonly artifact_register: ToolContract<ArtifactRegisterToolParams>;
  readonly artifact_create: ToolContract<ArtifactCreateToolParams>;
  readonly artifact_read: ToolContract<ArtifactReadToolParams>;
}

export function createPublicToolContracts(Type: any): PublicToolContracts;
export type ResearchReadToolParams = ToolParameters["research_read"];
export type JobStartToolParams = ToolParameters["job_start"];
export type JobStatusToolParams = ToolParameters["job_status"];
export type JobCollectToolParams = ToolParameters["job_collect"];
export type JobCancelToolParams = ToolParameters["job_cancel"];
export type JobProbeToolParams = ToolParameters["job_probe"];
export type JobReconcileToolParams = ToolParameters["job_reconcile"];
export type ArtifactRegisterToolParams = ToolParameters["artifact_register"];
export type ArtifactCreateToolParams = ToolParameters["artifact_create"];
export type ArtifactReadToolParams = ToolParameters["artifact_read"];
