/** Compact Skinn-style tool cards keep identity and execution state separate. */
import { stripVTControlCharacters } from 'node:util';
import { createPlainOutput } from './plain-output.mjs';

const ARGUMENT_KEYS = [
  'caseDirectory', 'case_directory', 'path', 'file_path', 'file', 'directory',
  'command', 'pattern', 'query', 'doi', 'url', 'ref', 'job_id', 'artifact_id',
  'request_file', 'node_id',
];
const MAX_ARGUMENT_WIDTH = 72;
const UNSAFE_TERMINAL_ESCAPE =
  /(?:\u001B\]|\u009D)[\s\S]*?(?:\u0007|\u001B\\|\u009C)|(?:\u001B[PX^_]|\u0090)[\s\S]*?(?:\u001B\\|\u009C)|(?:\u001B\[|\u009B)[0-?]*[ -/]*[@-~]|\u001B[@-_]/g;

function presentationTheme(theme) {
  return process.env.TERM === 'dumb' || 'NO_COLOR' in process.env
    ? { fg: (_, text) => stripVTControlCharacters(text), bold: text => stripVTControlCharacters(text) }
    : theme;
}

function textOf(result) {
  return (result?.content || [])
    .filter(block => block?.type === 'text' && typeof block.text === 'string')
    .map(block => block.text)
    .join('\n');
}

function sanitizeToolText(value) {
  return String(value)
    .replace(UNSAFE_TERMINAL_ESCAPE, '')
    .replace(/\x1B/g, '')
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n');
}

function statusMark(theme, context = {}) {
  if (context.isError) return theme.fg('error', '×');
  // `isPartial` is the lifecycle signal preserved by live rendering and replay.
  if (context.isPartial) return theme.fg('warning', '·');
  return theme.fg('success', '✓');
}

function compactArgument(value) {
  const normalized = String(value).replace(/\s+/g, ' ');
  if (normalized.length <= MAX_ARGUMENT_WIDTH) return normalized;
  if (!normalized.includes('/')) return `${normalized.slice(0, MAX_ARGUMENT_WIDTH - 1)}…`;
  const parts = normalized.split('/');
  const tail = parts.slice(-3).join('/');
  const prefixBudget = MAX_ARGUMENT_WIDTH - tail.length - 2;
  if (prefixBudget <= 0) return `${normalized.slice(0, MAX_ARGUMENT_WIDTH - 1)}…`;
  const prefixParts = [];
  for (const part of parts.slice(0, -3)) {
    const candidate = [...prefixParts, part].join('/');
    if (candidate.length > prefixBudget) break;
    prefixParts.push(part);
  }
  return `${prefixParts.join('/')}…/${tail}`;
}

function argumentText(args) {
  if (typeof args === 'string' && args) return args;
  if (!args || typeof args !== 'object' || Array.isArray(args)) return undefined;
  for (const key of ARGUMENT_KEYS) {
    if (typeof args[key] === 'string' && args[key]) return args[key];
  }
  return Object.values(args).find(value => typeof value === 'string' && value) || undefined;
}

function formatDuration(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs < 0) return undefined;
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(durationMs >= 10000 ? 0 : 1)}s`;
}

function compactToolLine(toolName, args, theme, context = {}, expanded, showToggle, durationMs) {
  const value = argumentText(args);
  const detail = value ? `  ${theme.fg('muted', compactArgument(value))}` : '';
  const duration = formatDuration(durationMs);
  const elapsed = duration ? `  ${theme.fg('muted', duration)}` : '';
  const toggle = showToggle ? `  ${theme.fg('accent', expanded ? '▴' : '▾')}` : '';
  return `${statusMark(theme, context)} ${theme.fg('toolTitle', theme.bold(toolName))}${detail}${elapsed}${toggle}`;
}

function textComponent(Text, candidate) {
  return candidate instanceof Text ? candidate : new Text('', 0, 0);
}

export function createCoRAgentToolRenderers({ Text }, names) {
  return Object.fromEntries(names.map(name => [name, {
    renderShell: 'self',
    renderCall(args, theme, context = {}) {
      theme = presentationTheme(theme);
      const state = context.state || {};
      const component = textComponent(Text, context.lastComponent || state.callComponent);
      component.setText(compactToolLine(name, args, theme, context, false, false));
      state.callComponent = component;
      return component;
    },
    renderResult(result, options = {}, theme, context = {}) {
      theme = presentationTheme(theme);
      const state = context.state || {};
      // A collapsed card only needs to know whether there is output. Avoid
      // joining and sanitizing a growing command log on every progress update.
      const hasOutput = (result?.content || []).some(block => block?.type === 'text' && Boolean(block.text));
      const isError = Boolean(context.isError || result?.isError);
      const resultContext = { ...context, isError };
      const hadCallComponent = context.lastComponent instanceof Text || state.callComponent instanceof Text;
      // Pi passes the previous result component as `lastComponent` on redraw.
      // The compact title must stay attached to the call component we own;
      // otherwise duration and the collapse arrow are written into an
      // invisible result component and disappear on the next render.
      const callComponent = textComponent(Text, state.callComponent || context.lastComponent);
      const durationMs = Number.isFinite(context.durationMs) ? context.durationMs
        : Number.isFinite(options.durationMs) ? options.durationMs
          : Number.isFinite(result?.durationMs) ? result.durationMs : undefined;
      const line = compactToolLine(name, context.args, theme, resultContext,
        Boolean(options.expanded), hasOutput, durationMs);
      callComponent.setText(line);
      state.callComponent = callComponent;
      if (!options.expanded || !hasOutput) {
        state.outputComponent = undefined;
        return new Text('', 0, 0);
      }
      const raw = sanitizeToolText(textOf(result));
      if (!hadCallComponent) return new Text(`${line}\n${raw}`, 0, 0);
      state.outputComponent ??= createPlainOutput(Text);
      state.outputComponent.setText(`\n${raw}`);
      return state.outputComponent;
    },
  }]));
}
