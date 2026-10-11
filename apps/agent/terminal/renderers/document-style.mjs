import { stripVTControlCharacters } from 'node:util';

const STATE_ROLES = {
  accent: ['active', 'running', 'queued', 'pending', 'submitted', 'researching', 'completing', 'preparing delivery',
    'recovering', 'checking recovery', 'checking continuation', 'preparing continuation'],
  warning: ['blocked', 'waiting', 'waiting for compute', 'needs attention', 'responding', 'task blocked',
    'automatic continuation off', 'status is stale', 'continuation check overdue'],
  error: ['failed', 'error', 'timed_out', 'connection lost'],
  success: ['completed', 'succeeded', 'success'],
  muted: ['paused', 'cancelled', 'canceled', 'idle', 'closed', 'ended', 'unknown', 'no current task', 'checking status'],
};
const stateRole = text => Object.entries(STATE_ROLES).find(([, states]) => states.includes(text.toLowerCase()))?.[0];

/** Highlight source text without changing its content or logical line anchors. */
export function styleDocument(text, { theme, monochrome, markdown = false }) {
  const plain = stripVTControlCharacters(String(text ?? ''));
  const current = typeof theme === 'function' ? theme() : theme;
  if (monochrome || !current) return plain;
  const fg = (role, value) => current.fg(role, value);
  const inline = value => value.replace(/(`+)([^`\n]+)\1/g, code => fg('mdCode', code));
  const scalar = (value, status = false) => {
    const role = status && (stateRole(value) || (/^Continuation error:/.test(value) ? 'error' : undefined));
    if (role) return fg(role, value);
    if (/^(?:—|\[\]|\{\}|""|Unknown|Not recorded)$/.test(value)) return fg('muted', value);
    if (/^(?:true|false|On|Off|Yes|No)$/.test(value)) return fg('syntaxKeyword', value);
    if (/^-?\d[\d,.]*(?:[km]|%)?(?:\s*\/\s*\d[\d,.]*[km]?)?(?: \(\d+%\))?$/.test(value)) return fg('syntaxNumber', value);
    if (/^\/[a-z][\w-]*(?:\s|$)/i.test(value)) return fg('mdCode', value);
    return inline(value);
  };
  let fence;
  const source = plain.split('\n');
  return source.map((line, index) => {
    if (markdown) {
      const marker = /^\s*(`{3,}|~{3,})/.exec(line)?.[1];
      if (marker) {
        if (!fence) fence = marker;
        else if (marker[0] === fence[0] && marker.length >= fence.length) fence = undefined;
        return fg('mdCodeBlockBorder', line);
      }
      if (fence) return fg('mdCodeBlock', line);
      if (/^\s{0,3}#{1,6}\s/.test(line) || /^(?:Sources|Limitations)$/.test(line)) return fg('mdHeading', line);
      if (/^\s*>/.test(line)) return fg('mdQuote', line);
      const metadata = /^(Working directory:|SHA256:)(.*)$/.exec(line);
      if (metadata) return fg('accent', metadata[1]) + metadata[2];
      return inline(line).replace(/^(\s*)([-*+] |\d+\. )/, (_, space, bullet) => space + fg('mdListBullet', bullet));
    }
    if (/^─+$/.test(line)) return fg('mdHr', line);
    if (/^─+$/.test(source[index + 1] || '') || /^(?:By model|Compute jobs|Research problems|Related compute jobs|Relations \(references to the same problems\))$/.test(line)) return fg('mdHeading', line);
    const parts = line.split(' · ');
    return parts.map((part, partIndex) => {
      const field = /^(\s*(?:• )?)([\w][\w /().-]*:)(\s*)(.*)$/.exec(part);
      if (!field) return scalar(part, parts.length > 1 && partIndex > 0);
      const [, prefix, label, space, value] = field;
      const status = /^(?:state|status|execution|collection|action outcome):$/i.test(label);
      return prefix + fg('accent', label) + space + scalar(value, status);
    }).join(fg('muted', ' · '));
  }).join('\n');
}
