import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdir, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { pinnedPiSource, TEST_ROOT } from './test-environment.mjs';
import { createCoRAgentToolRenderers } from '../../../apps/agent/terminal/renderers/tools.mjs';
import { createChatView } from '../../../apps/agent/terminal/chat.mjs';

const source = pinnedPiSource();
const components = await import(pathToFileURL(join(source, 'packages/tui/src/index.ts')));
const themes = await import(pathToFileURL(join(source, 'packages/coding-agent/src/modes/interactive/theme/theme.ts')));
themes.initTheme('dark');
const theme = { fg: (_, value) => value, bold: value => value };

test('expanded tool output matches Pi text through append, replacement, resize and split escapes', () => {
  const renderer = createCoRAgentToolRenderers(components, ['bash']).bash;
  const state = {}, args = { command: 'fixture' };
  renderer.renderCall(args, theme, { state });
  const cases = [
    ['', ''], ['\n\t  \n', '\n\t  \n'], ['line', 'line'], ['line one\n', 'line one\n'],
    ['line one\n中文🙂\twords e\u0301', 'line one\n中文🙂\twords e\u0301'],
    ['line one\n中文🙂\twords e\u0301\n\n\t\nnext', 'line one\n中文🙂\twords e\u0301\n\n\t\nnext'],
    ['replacement\n', 'replacement\n'], ['short', 'short'],
    ['short\x1b[31', 'short31'], ['short\x1b[31mred\x1b[0m', 'shortred'],
    ['short\x1b[31mred\x1b[0m\r\nnext', 'shortred\nnext'],
    ['short\x1b[31mred\x1b[0m\r\nnext\x1b]52;c;fixture\x07', 'shortred\nnext'],
    ['\n'.repeat(200) + 'tail', '\n'.repeat(200) + 'tail'],
  ];
  for (const [raw, sanitized] of cases) {
    const result = renderer.renderResult({ content: [{ type: 'text', text: raw }] }, { expanded: true }, { ...theme }, { state, args });
    for (const width of [80, 17, 1, 80]) {
      assert.deepEqual(result.render(width), new components.Text(`\n${sanitized}`, 0, 0).render(width));
      assert.equal(result.render(width), result.render(width), 'unchanged output reuses its layout');
    }
    result.invalidate();
    assert.deepEqual(result.render(80), new components.Text(`\n${sanitized}`, 0, 0).render(80));
  }
});

test('expanded logs wrap appended lines without rewrapping completed output', async () => {
  let constructions = 0;
  class Text extends components.Text {
    constructor(text, ...args) { super(text, ...args); this.source = text; constructions++; }
    setText(text) { super.setText(text); this.source = text; this.lastSource = undefined; }
    render(width) {
      this.lastSource = this.source; this.lastWidth = width;
      return super.render(width);
    }
  }
  const renderer = createCoRAgentToolRenderers({ ...components, Text }, ['bash']).bash;
  const state = {}, args = { command: 'fixture' };
  renderer.renderCall(args, theme, { state });
  let text = 'Completed evidence 中文 with enough text to wrap at narrow widths.\n'.repeat(3000) + 'partial';
  const show = () => renderer.renderResult({ content: [{ type: 'text', text }] }, { expanded: true }, theme, { state, args }).render(60);
  show(); const initialConstructions = constructions;
  const durations = [];
  let appendedCharacters = 0;
  for (let index = 0; index < 40; index++) {
    const suffix = ` continuation ${index}\nNext 中文 line ${index}`;
    appendedCharacters += suffix.length;
    text += suffix;
    const start = performance.now(); show(); durations.push(performance.now() - start);
  }
  durations.sort((a, b) => a - b);
  await mkdir(TEST_ROOT, { recursive: true });
  await writeFile(join(TEST_ROOT, 'terminal-expanded-output-performance.json'), JSON.stringify({
    initial_lines: 3000, updates: 40, appended_characters: appendedCharacters,
    new_line_components: constructions - initialConstructions,
    p50_ms: durations[20], p95_ms: durations[38], max_ms: durations.at(-1),
  }));
  assert.ok(constructions - initialConstructions <= 80, 'append layout should reuse completed output lines');
  assert.deepEqual(show(), new components.Text(`\n${text}`, 0, 0).render(60));
});

test('an expanded large log fits the transcript without exhausting the JavaScript argument stack', () => {
  const chat = createChatView({ components, theme: themes.theme, markdownTheme: themes.getMarkdownTheme(), requestRender() {} });
  chat.update({ entries: [
    { id: 1, kind: 'pi.assistant', model: [{ role: 'assistant', content: [
      { type: 'toolCall', id: 'large', name: 'bash', arguments: { command: 'fixture' } },
    ] }] },
    { id: 2, kind: 'pi.tool-result', model: [{ role: 'toolResult', toolCallId: 'large', isError: false,
      content: [{ type: 'text', text: 'x\n'.repeat(150_000) + 'last evidence' }] }] },
  ], docs: {} });
  chat.toggleTools();
  const lines = chat.render(80);
  assert.ok(lines.length > 150_000);
  assert.match(lines.at(-1), /last evidence/);
});
