/**
 * Render sanitized tool output as independent plain-text lines. Pi's Text
 * component still owns wrapping and Unicode cell measurement; completed lines
 * keep their own width cache while a live command appends new lines.
 */
export function createPlainOutput(Text) {
  let source = '', lines = [], components = [], rendered = new Map(), empty = [];

  function rebuild(value) {
    const next = String(value).split('\n');
    const common = source && String(value).startsWith(source)
      ? Math.min(lines.length, next.length)
      : 0;
    const nextComponents = [];
    for (let index = 0; index < next.length; index++) {
      if (index < common && next[index] === lines[index]) nextComponents.push(components[index]);
      else nextComponents.push(next[index].trim() === '' ? undefined : new Text(next[index], 0, 0));
    }
    source = String(value); lines = next; components = nextComponents; rendered = new Map();
  }

  return {
    setText(value) { if (String(value) !== source) rebuild(value); },
    invalidate() { rendered.clear(); for (const component of components) component?.invalidate(); },
    render(width) {
      if (!source.trim()) return empty;
      if (rendered.has(width)) return rendered.get(width);
      const output = [];
      for (const component of components) {
        if (!component) { output.push(' '.repeat(width)); continue; }
        for (const line of component.render(width)) output.push(line);
      }
      rendered.set(width, output);
      return output;
    },
  };
}
