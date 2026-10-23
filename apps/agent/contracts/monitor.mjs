import limits from "../../../contracts/monitor/jobs/limits.json" with { type: "json" };

export const JOB_EVENT_IDS_LIMIT = limits.max_event_ids;

/** Canonical Monitor methods shared by Host transports and clients. */
export const MONITOR_METHODS = Object.freeze([
  "monitor/overview", "monitor/tasks", "monitor/task/read", "monitor/task/pause",
  "monitor/task/resume", "monitor/task/cancel", "monitor/jobs", "monitor/job/read",
  "monitor/job/cancel", "monitor/runs", "monitor/run/read", "monitor/health",
]);

export const MONITOR_MUTATIONS = Object.freeze([
  "monitor/task/pause", "monitor/task/resume", "monitor/task/cancel", "monitor/job/cancel",
]);

export const MONITOR_SERVICE_ID = "coragent.monitor";
