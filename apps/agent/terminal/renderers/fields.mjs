/** Keep empty collections explicit and nested records aligned in read-only views. */
export function formatFields(value, indent = '') {
  const entries = value && typeof value === 'object' && !Array.isArray(value)
    ? Object.entries(value).filter(([key]) => key !== 'schema_version') : null;
  const inline = value === null || value === undefined ? '—'
    : typeof value !== 'object' ? String(value === '' ? '""' : value)
    : Array.isArray(value) ? (value.length ? undefined : '[]')
    : entries.length ? undefined : '{}';
  if (inline !== undefined) return indent + inline.replaceAll('\n', '\n' + indent);
  if (Array.isArray(value)) return value.map(item => {
    const child = formatFields(item, indent + '  ');
    return `${indent}• ${child.slice(indent.length + 2)}`;
  }).join('\n');
  return entries.map(([key, item]) => {
    const childIndent = indent + '  ';
    const child = formatFields(item, childIndent);
    const nested = item && typeof item === 'object'
      && (Array.isArray(item) ? item.length : Object.keys(item).some(key => key !== 'schema_version'));
    return `${indent}${key.replaceAll('_', ' ')}:${nested ? '\n' + child : ' ' + child.slice(childIndent.length)}`;
  }).join('\n');
}
