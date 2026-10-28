import { stripVTControlCharacters, isDeepStrictEqual } from "node:util";
import { taskStateLabel } from "../commands/monitor.mjs";

const clean = value => stripVTControlCharacters(String(value ?? "")).replace(/[\x00-\x1f\x7f-\x9f]/gu, " ");
const labels = { "pi.run": "Agent", "pi.generation": "Model", "pi.compaction": "Compaction", "pi.tool": "Tool" };
const taskName = task => labels[task.kind] || clean(task.kind);
const time = value => Number.isFinite(value) ? new Date(value).toLocaleTimeString() : "unknown";
const stale = value => !value || !Number.isFinite(Date.parse(value.updated_at)) || Date.now() - Date.parse(value.updated_at) > 30_000;

export function runtimeSummary(runtime, view, error) {
  if (error || stale(runtime)) return "Status unavailable · /tasks to refresh";
  if (view?.docs?.["pi.live"]?.compactionFailure) return "Compaction failed · /compact to retry";
  if (runtime.counts.blocked) return "Needs attention · /tasks";
  if (view?.failure && !view.docs?.["pi.live"]?.run) return `${clean(view.failure.summary)} · /tasks`;
  if (runtime.tasks.some(task => task.kind === "pi.compaction")) return "Compacting context";
  if (runtime.counts.sleeping && !runtime.counts.running) {
    const until = Math.min(...runtime.tasks.filter(task => task.state === "sleeping").map(task => task.until));
    return `Waiting · next check ${time(until)}`;
  }
  if (runtime.counts.running || runtime.counts.ready) return "Running";
  if (runtime.counts.waiting) return "Waiting for tasks";
  return runtime.scheduling === "paused" ? "Paused" : "Idle";
}

export function createSessionInsights({ theme, truncateToWidth, wrapTextWithAnsi,
  monochrome = process.env.TERM === "dumb" || "NO_COLOR" in process.env }) {
  let state = {};
  let revision = 0, sidebarCache;
  const fit = (text, width) => truncateToWidth(text, Math.max(1, width));
  const color = (name, text) => monochrome ? text : theme.fg(name, text);
  const taskLines = task => [
    `${taskName(task)} #${task.id}: ${task.state}${task.reason ? ` (${task.reason})` : ""}`,
    ...(task.restarts ? [`Restarts: ${task.restarts}`] : []),
    ...(task.state === "sleeping" ? [`Next check: ${time(task.until)}`] : []),
    ...(task.waiting_on?.length ? [`Waiting for: ${task.waiting_on.join(", ")}`] : []),
    ...(task.retryable ? [`Retry: /retry ${task.id}`] : []),
  ];
  return {
    update(value) {
      // The sidebar uses failure metadata, never the streaming transcript.
      if (value.view) value = { ...value, view: { failure: value.view.failure,
        docs: { "pi.live": { compactionFailure: value.view.docs?.["pi.live"]?.compactionFailure } } } };
      const changed = Object.entries(value).some(([key, item]) => !isDeepStrictEqual(state[key], item));
      state = { ...state, ...value };
      if (changed) revision++;
      return changed;
    },
    activity: { invalidate() {}, render(width) {
      return [fit(` ${color("muted", `Session: ${runtimeSummary(state.runtime, state.view, state.runtimeError)}`)}`, width)];
    } },
    sidebar: { invalidate() { sidebarCache = undefined; }, render(width) {
      const { monitor, research, runtime } = state;
      const key = `${width}:${revision}:${stale(monitor)}:${stale(runtime)}`;
      if (sidebarCache?.key === key) return sidebarCache.lines;
      const monitorUnavailable = state.monitorError || stale(monitor);
      const task = !monitorUnavailable && monitor.task;
      const brief = !state.researchError && research?.result;
      // A previous task's research must never become the new task's conclusion.
      const sameTask = task && research?.task?.user_task_id === task.user_task_id;
      const focus = new Set(sameTask ? [...(brief?.scope?.focus_node_ids || []), ...(brief?.scope?.entry_node_ids || [])] : []);
      const questions = (brief?.findings || []).filter(item => item.kind === "node" && focus.has(item.ref));
      const rows = ["Research & jobs", "", runtimeSummary(runtime, state.view, state.runtimeError), "",
        monitorUnavailable ? "Monitor unavailable" : task ? `${clean(task.title)} · ${taskStateLabel(task.state)}` : "No current research task",
        ...(task?.progress?.summary ? [clean(task.progress.summary).slice(0, 240)] : []),
        ...(task?.reason ? [clean(task.reason).slice(0, 160)] : []),
        ...(task?.next_action ? [`Next: ${clean(task.next_action).slice(0, 200)}`] : []), "",
        ...questions.slice(0, 3).map(item => `Question: ${clean(item.title || item.ref)}`),
        ...(state.researchError ? ["Research unavailable · /research"] : task && !sameTask ? ["Research updating · /research"]
          : !questions.length ? ["No linked research questions"] : []), "",
        monitorUnavailable ? "Jobs unavailable" : `Jobs: ${monitor.jobs?.counts?.running ?? 0} running · ${monitor.jobs?.counts?.queued ?? 0} queued`,
        ...(!monitorUnavailable ? (monitor.jobs?.active || []).slice(0, 4).map(job => `${clean(job.job_id)} · ${clean(job.state)}`) : []),
        ...(!monitorUnavailable && (monitor.jobs?.active_omitted || (monitor.jobs?.active || []).length > 4) ? ["More jobs: /monitor jobs"] : []), "",
        ...(!state.runtimeError && !stale(runtime) ? runtime.tasks.filter(task => task.retryable).slice(0, 2).flatMap(taskLines) : []),
        ...(task && (["paused", "blocked"].includes(task.state) || task.execution_recovery?.state === "attention_required")
          ? [`Resume: /monitor task resume ${task.user_task_id}`] : []),
        "/research · /monitor · /tasks", "/sidebar off to hide",
      ];
      const lines = rows.flatMap((row, index) => wrapTextWithAnsi(clean(row), Math.max(1, width - 2))
        .map(line => fit(` ${index === 0 ? color("accent", line) : line}`, width)));
      sidebarCache = { key, lines }; return lines;
    } },
    details() {
      const { runtime, view } = state;
      const failed = view?.docs?.["pi.live"]?.compactionFailure;
      return [runtimeSummary(runtime, view, state.runtimeError),
        ...(state.runtimeError ? [clean(state.runtimeError)] : []),
        ...(failed ? [`Compaction: ${clean(failed.error || failed.reason)}`, "Retry compaction: /compact"] : []),
        ...(view?.failure ? [clean(view.failure.detail)] : []), "",
        ...(!state.runtimeError && !stale(runtime) ? [
          `Queued inputs: ${runtime.queued_inputs}`, ...runtime.tasks.flatMap(task => [...taskLines(task), ""]),
          ...(runtime.omitted ? [`${runtime.omitted} more tasks; retryable tasks are listed first.`] : []),
        ] : []),
        "Research task controls: /monitor", "Retry only tasks paused at the restart limit: /retry",
      ].join("\n");
    },
  };
}
