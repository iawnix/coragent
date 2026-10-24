import { formatMonitor, taskStateLabel } from '../commands/monitor.mjs';
import { stripVTControlCharacters } from 'node:util';

/** Pure presentation of durable usage, current context and operational observations. */
export const formatTokens = value => Number.isFinite(value)
  ? value >= 1e6 ? `${(value / 1e6).toFixed(1)}m` : value >= 1e3 ? `${(value / 1e3).toFixed(1)}k` : `${Math.round(value)}` : 'Unknown';

export function usageTotals(ledger) {
  const rows = Object.values(ledger?.models || {});
  if (!rows.length) return null;
  const keys = ['input', 'output', 'cacheRead', 'cacheWrite', 'reasoning', 'totalTokens'];
  return Object.fromEntries(keys.map(key => [key, rows.every(row => Number.isFinite(row[key]))
    ? rows.reduce((sum, row) => sum + (Number.isFinite(row[key]) ? row[key] : 0), 0) : null]));
}

export function contextMatches(view, telemetry) {
  return telemetry && telemetry.entryId === (view?.entries?.at(-1)?.id ?? null)
    && telemetry.firstEntryId === (view?.entries?.[0]?.id ?? null)
    && contextModelMatches(view, telemetry);
}

function contextModelMatches(view, telemetry) {
  const model = view?.docs?.['pi.agent']?.model;
  return model && telemetry?.model
    && model.provider === telemetry.model.provider && model.modelId === telemetry.model.modelId;
}

export function activityStatus({ monitor, monitorError, sessionId, now = Date.now() }) {
  const scoped = monitor?.session_id === sessionId ? monitor : null;
  const updated = Date.parse(scoped?.updated_at);
  let connection = 'Connected', color = 'muted', detail = null;
  if (monitorError) {
    connection = 'Disconnected'; color = 'error'; detail = 'Monitor is unavailable. Reconnect to refresh the current snapshot.';
  } else if (!scoped) {
    connection = 'Connecting'; detail = 'Waiting for a Monitor snapshot for this session.';
  } else if (!Number.isFinite(updated) || now - updated > 30_000) {
    connection = 'Unknown'; color = 'warning'; detail = 'Status is stale. Refresh Monitor before relying on these details.';
  }
  const taskState = detail ? 'Unknown' : scoped.task ? taskStateLabel(scoped.task.state) : 'None';
  const running = detail ? null : scoped.jobs?.counts?.running ?? null;
  const queued = detail ? null : scoped.jobs?.counts?.queued ?? null;
  const jobSummary = running === null || queued === null ? 'Unknown' : `${running} running, ${queued} queued`;
  return { text: `Monitor: ${connection} · Task: ${taskState} · Job: ${jobSummary}`,
    connection, color, taskState, jobSummary, detail, running, queued };
}

export function createStatusPresentation({ session, theme, truncateToWidth, visibleWidth, ring = true,
  monochrome = process.env.TERM === 'dumb' || 'NO_COLOR' in process.env }) {
  let view, telemetry, telemetryError, monitor, monitorError;
  const fit = (text, width) => truncateToWidth(text, Math.max(1, width));
  const modelLabel = () => {
    const agent = view?.docs?.['pi.agent'] || {};
    return { model: agent.model?.modelId || 'Unknown', provider: agent.model?.provider,
      thinking: agent.thinkingLevel || 'off' };
  };
  const contextState = () => {
    const current = !telemetryError && contextMatches(view, telemetry);
    return {
      tokens: current ? telemetry.contextTokens : null,
      capacity: contextModelMatches(view, telemetry) ? telemetry.contextWindow : null,
      budget: current ? telemetry.inputBudgetTokens : null,
      pending: telemetryError ? 'Unavailable' : current ? 'Unknown' : 'Updating',
    };
  };
  const footer = {
    invalidate() {},
    render(width) {
      const w = Math.max(1, width - 2); const { model, provider, thinking } = modelLabel();
      const identity = `${provider ? `${provider}/` : ''}${model} · Thinking: ${thinking} · Workspace: ${session.workspaceId}`;
      const variants = [
        `${identity} · Session: ${session.sessionId}`,
        `${identity} · Session: ${session.sessionId.slice(0,8)}…`,
        `${model} · ${thinking} · ${session.workspaceId} · ${session.sessionId.slice(0,8)}…`,
        `${model} · ${thinking} · ${session.workspaceId}`,
      ];
      const suffix = ` · ${thinking} · ${session.workspaceId}`;
      const first = variants.find(value => visibleWidth(value) <= w)
        || `${fit(model, Math.max(1,w-visibleWidth(suffix)))}${suffix}`;
      const { tokens, capacity, budget: inputBudget, pending } = contextState();
      const percent = Number.isFinite(tokens) && capacity > 0 ? tokens / capacity * 100 : null;
      const icon = ring && percent !== null ? `${['○','◔','◑','◕','●'][Math.min(4, Math.round(percent / 25))]} ` : '';
      const context = `${icon}Context: ${Number.isFinite(tokens) ? formatTokens(tokens) : pending}/${formatTokens(capacity)}${percent === null ? '' : ` (${percent.toFixed(0)}%)`}`;
      const budget = Number.isFinite(inputBudget) ? ` · Budget: ${formatTokens(inputBudget)}` : '';
      const total = formatTokens(usageTotals(view?.docs?.['pi.usage'])?.totalTokens);
      const second = `${context}${budget} · Total tokens: ${total}`;
      const short = `${icon}Ctx: ${percent === null ? pending : `${percent.toFixed(0)}%`}${budget} · Tokens: ${total}`;
      const budgetPercent = Number.isFinite(tokens) && inputBudget > 0 ? tokens / inputBudget * 100 : null;
      const pressure = Math.max(percent ?? 0, budgetPercent ?? 0);
      const color = pressure >= 90 ? 'error' : pressure >= 70 ? 'warning' : 'muted';
      const lines = [fit(first,w), fit(visibleWidth(second) <= w ? second : short,w)];
      return lines.map((line, index) => ` ${monochrome ? stripVTControlCharacters(line) : theme.fg(index ? color : 'muted', line)}`);
    },
  };
  const activity = { invalidate() {}, render(width) {
    const state = activityStatus({monitor,monitorError,sessionId:session.sessionId});
    const text = monochrome ? state.text
      : `${theme.fg('muted','Monitor: ')}${theme.fg(state.color,state.connection)}${theme.fg('muted',state.text.slice(`Monitor: ${state.connection}`.length))}`;
    return width > 0 ? [truncateToWidth(` ${text}`,width)] : [];
  } };
  return { footer, activity,
    update(value) {
      if ('view' in value) view = value.view;
      if ('telemetry' in value) telemetry = value.telemetry;
      if ('telemetryError' in value) telemetryError = value.telemetryError;
      if ('monitor' in value) monitor = value.monitor;
      if ('monitorError' in value) {
        monitorError = value.monitorError;
      }
    },
    usageDetails() {
      const totals = usageTotals(view?.docs?.['pi.usage']);
      const count = value => Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
      const { tokens, capacity, budget, pending } = contextState();
      const rows = Object.entries(view?.docs?.['pi.usage']?.models || {})
        .map(([model, usage]) => `${model}: ${count(usage.totalTokens)}`);
      return [`Total tokens: ${count(totals?.totalTokens)}`,
        `Input: ${count(totals?.input)} · Output: ${count(totals?.output)}`,
        `Cache read: ${count(totals?.cacheRead)} · Cache write: ${count(totals?.cacheWrite)}`,
        `Reasoning: ${count(totals?.reasoning)}`,
        `Context: ${Number.isFinite(tokens) ? count(tokens) : pending} / ${count(capacity)}`,
        `Input budget: ${count(budget)}`,
        ...(telemetryError ? [`Context refresh: ${telemetryError}`] : []),
        ...(rows.length ? ['', 'By model', ...rows] : [])].join('\n');
    },
    monitorDetails() {
      const state = activityStatus({monitor,monitorError,sessionId:session.sessionId});
      return [`Status: ${state.text}`,
        ...(state.detail ? [state.detail] : []),
        ...(monitor && !state.detail ? [formatMonitor('monitor/overview', monitor)] : []),
        ...(monitorError ? [`Connection: ${monitorError}`] : [])].join('\n');
    },
  };
}
