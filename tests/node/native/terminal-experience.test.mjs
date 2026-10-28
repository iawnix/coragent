import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdir, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { stripVTControlCharacters } from 'node:util';
import { pinnedPiSource, TEST_ROOT } from './test-environment.mjs';
import { createChatView } from '../../../apps/agent/terminal/chat.mjs';
import { createWorkingStatus } from '../../../apps/agent/terminal/status/working.mjs';
import { createViewStream, createViewReplica } from '../../../apps/agent/transport/view-stream.mjs';

const source = pinnedPiSource();
const fromSource = path => import(pathToFileURL(join(source, path)));
const components = await fromSource('packages/tui/src/index.ts');
const themes = await fromSource('packages/coding-agent/src/modes/interactive/theme/theme.ts');
const { renderLayoutFrame } = await fromSource('packages/tui/src/layout.ts');
themes.initTheme('dark');
const chatView = () => createChatView({ components, theme: themes.theme,
  markdownTheme: themes.getMarkdownTheme(), requestRender() {} });
const entry = (id, text) => ({ id, kind: 'pi.assistant', model: [
  { role: 'assistant', content: [{ type: 'text', text }] },
] });

test('token updates do not inspect immutable historical entries', () => {
  let reads = 0;
  const entries = new Proxy(Array.from({ length: 1000 }, (_, id) => entry(id, `History ${id}`)), {
    get(target, key, receiver) {
      if (/^\d+$/u.test(String(key))) reads++;
      return Reflect.get(target, key, receiver);
    },
  });
  const stream = createViewStream();
  stream.next({ entries, docs: {} });
  for (let index = 0; index < 60; index++) {
    const frame = stream.next({ entries, docs: { 'pi.live': { generation: { text: `token ${index}` } } } });
    assert.equal(frame.entries, undefined);
  }
  assert.equal(reads, 0, 'streaming must not scan unchanged conversation history');
});

test('fresh watch arrays compare immutable entry identities without reading message bodies', () => {
  let reads = 0;
  const make = id => ({ id, kind: 'pi.assistant', get model() { reads++; return [{ role: 'assistant', content: 'stable' }]; } });
  const first = Array.from({ length: 1000 }, (_, id) => make(id));
  const stream = createViewStream();
  stream.next({ entries: first, docs: {} });
  for (let index = 0; index < 60; index++) {
    const frame = stream.next({ entries: first.map(item => make(item.id)), docs: { 'pi.live': { generation: { text: index } } } });
    assert.equal(frame.entries, undefined);
  }
  assert.equal(reads, 0, 'identity comparison must not deserialize immutable message bodies');
});

test('tool progress leaves historical messages untouched and records a repeatable workload', async () => {
  let reads = 0;
  const entries = Array.from({ length: 1000 }, (_, id) => {
    const item = entry(id, `History ${id}: 中文 **measurement**\n\n- evidence\n- result`);
    const content = item.model[0].content;
    Object.defineProperty(item.model[0], 'content', { get() { reads++; return content; } });
    return item;
  });
  entries.push({ id: 1000, kind: 'pi.assistant', model: [{ role: 'assistant', content: [
    { type: 'toolCall', id: 'running', name: 'bash', arguments: { command: 'fixture' } },
  ] }] });
  let redraws = 0;
  const chat = createChatView({ components, theme: themes.theme, markdownTheme: themes.getMarkdownTheme(),
    requestRender() { redraws++; } });
  const next = output => ({ entries, docs: { 'pi.live': { run: {}, tools: [
    { callId: 'running', name: 'bash', status: 'running', output },
  ] } } });
  chat.update(next('start')); const collapsed = chat.render(100);
  reads = 0; redraws = 0;
  const durations = [];
  for (let index = 0; index < 60; index++) {
    const start = performance.now();
    chat.update(next('fixture progress\n'.repeat((index + 1) * 100)));
    assert.equal(chat.render(100), collapsed, 'hidden progress leaves the displayed transcript unchanged');
    durations.push(performance.now() - start);
  }
  durations.sort((a, b) => a - b);
  await mkdir(TEST_ROOT, { recursive: true });
  await writeFile(join(TEST_ROOT, 'terminal-tool-progress-performance.json'), JSON.stringify({
    history_messages: 1000, updates: 60, history_content_reads: reads,
    p50_ms: durations[30], p95_ms: durations[57], max_ms: durations.at(-1),
  }));
  assert.equal(reads, 0, 'tool progress must not revisit finalized message content');
  assert.equal(redraws, 0, 'hidden progress must not schedule terminal redraws');
  chat.toggleTools();
  assert.match(chat.render(100).join('\n'), /fixture progress/);
});

test('static work status repaints immediately even when the transcript has no changes', t => {
  let redraws = 0;
  const status = createWorkingStatus({ ...components, theme: themes.theme, animated: false,
    requestRender() { redraws++; }, fallback: { render: () => ['Idle'] } });
  t.after(() => status.dispose());
  status.setActive(true);
  status.update({ docs: { 'pi.live': { run: {} } } });
  assert.equal(redraws, 1);
  assert.match(status.render(80).join('\n'), /Working/);
  status.update({ docs: { 'pi.live': { run: {}, tools: [{ name: 'bash', status: 'running' }] } } });
  assert.equal(redraws, 2);
  assert.match(status.render(80).join('\n'), /Running bash/);
  status.update({ docs: {} });
  assert.equal(redraws, 3);
  assert.deepEqual(status.render(80), ['Idle']);
});

test('run metadata changes do not invalidate the transcript', () => {
  const chat = chatView();
  const entries = [entry(1, 'A stable response')];
  const tools = [];
  chat.update({ entries, docs: { 'pi.live': { run: { taskId: 1 }, tools } } });
  const rendered = chat.render(80);
  chat.update({ entries, docs: { 'pi.live': { run: { taskId: 1, updatedAt: 2 }, tools } } });
  assert.equal(chat.render(80), rendered);
});

test('live tool cards show persisted completion and compaction removes old results', () => {
  const chat = chatView();
  const message = { content: [{ type: 'toolCall', id: 'running', name: 'bash', arguments: { command: 'fixture' } }] };
  const docs = { 'pi.live': { run: {}, generation: { message }, tools: [
    { callId: 'running', status: 'running', output: 'partial output' },
  ] } };
  chat.update({ entries: [], docs }); chat.toggleTools();
  assert.match(chat.render(80).join('\n'), /partial output/);
  const result = { id: 1, kind: 'pi.tool-result', model: [{ role: 'toolResult', toolCallId: 'running',
    content: [{ type: 'text', text: 'final failure' }], isError: true, durationMs: 2500 }] };
  chat.update({ entries: [result], docs });
  const finished = stripVTControlCharacters(chat.render(80).join('\n'));
  assert.match(finished, /× bash.*2\.5s/);
  assert.match(finished, /final failure/);
  assert.doesNotMatch(finished, /partial output/);
  chat.update({ entries: [], docs });
  assert.match(chat.render(80).join('\n'), /partial output/);
  assert.doesNotMatch(chat.render(80).join('\n'), /final failure/);
});

test('reading history keeps the same message when the terminal width changes', () => {
  const chat = chatView();
  const scroll = new components.ScrollView(chat, { follow: 'end', primary: true });
  chat.setScrollView?.(scroll);
  const frame = width => renderLayoutFrame(scroll, width, 12, () => {});
  chat.update({ entries: Array.from({ length: 60 }, (_, id) => entry(id,
    `Message ${id}: ` + '中文 text with wrapping. '.repeat(4))), docs: {} });
  frame(100);
  const lines = chat.render(100);
  scroll.scrollTo(lines.findIndex(line => stripVTControlCharacters(line).includes('Message 30:')));
  assert.match(stripVTControlCharacters(frame(100).lines[0]), /Message 30:/);
  assert.match(stripVTControlCharacters(frame(50).lines[0]), /Message 30:/);
  assert.equal(scroll.isFollowingEnd, false);
});

test('new output preserves a reader position and explicit follow resumes at the live edge', () => {
  const chat = chatView();
  const scroll = new components.ScrollView(chat, { follow: 'end', primary: true });
  chat.setScrollView(scroll);
  const entries = Array.from({ length: 60 }, (_, id) => entry(id, `Message ${id}`));
  const next = text => ({ entries, docs: { 'pi.live': { run: {}, generation: {
    message: { content: [{ type: 'text', text }] },
  } } } });
  const frame = () => renderLayoutFrame(scroll, 80, 12, () => {});
  chat.update(next('Initial response')); frame();
  scroll.scrollTo(30); const reading = frame().lines;
  chat.update(next('New streamed response\n'.repeat(100)));
  assert.deepEqual(frame().lines, reading);
  assert.equal(scroll.isFollowingEnd, false);
  scroll.scrollToEnd();
  assert.match(stripVTControlCharacters(frame().lines.join('\n')), /New streamed response/);
  assert.equal(scroll.isFollowingEnd, true);
});

test('expanding a tool at the bottom keeps its header visible instead of jumping past the output', () => {
  const chat = chatView();
  const scroll = new components.ScrollView(chat, { follow: 'end', primary: true });
  chat.setScrollView?.(scroll);
  const frame = () => renderLayoutFrame(scroll, 80, 12, () => {});
  const entries = Array.from({ length: 20 }, (_, id) => entry(id, `Message ${id}`));
  entries.push({ id: 20, kind: 'pi.assistant', model: [{ role: 'assistant', content: [
    { type: 'toolCall', id: 'result', name: 'bash', arguments: { command: 'fixture' } },
  ] }] }, { id: 21, kind: 'pi.tool-result', model: [{ role: 'toolResult', toolCallId: 'result',
    content: [{ type: 'text', text: 'Inspect this evidence\n'.repeat(100) }], isError: false }] });
  chat.update({ entries, docs: {} });
  frame();
  assert.equal(scroll.isFollowingEnd, true);
  const y = chat.render(80).findIndex(line => stripVTControlCharacters(line).includes('bash'));
  chat.handleMouse({ type: 'click', button: 'left', y });
  assert.match(stripVTControlCharacters(frame().lines.join('\n')), /bash.*fixture/);
  assert.equal(scroll.isFollowingEnd, false);
  scroll.scrollToEnd(); frame();
  assert.equal(scroll.isFollowingEnd, true);
});

test('full-screen streaming accepts Chinese input and paste without clearing the screen', async t => {
  const { VirtualTerminal } = await fromSource('packages/tui/test/virtual-terminal.ts');
  const terminal = new VirtualTerminal(100, 24);
  const tui = new components.TuiAltScreen(terminal);
  const editor = new components.Editor(tui, themes.getEditorTheme());
  const chat = createChatView({ components, theme: themes.theme, markdownTheme: themes.getMarkdownTheme(),
    requestRender: () => tui.requestRender() });
  const scroll = new components.ScrollView(chat, { follow: 'end', primary: true });
  chat.setScrollView(scroll);
  tui.setLayoutRoot(new components.VStack([
    { component: scroll, grow: 1, basis: 0, minSize: 0 }, { component: editor, shrink: 0 },
  ]));
  tui.setFocus(editor);
  t.after(async () => { tui.stop(); await terminal.flush(); terminal.dispose?.(); });
  let bytes = 0, clears = 0, submissions = 0;
  const write = terminal.write.bind(terminal);
  terminal.write = data => { bytes += Buffer.byteLength(data); clears += data.split('\x1b[2J').length - 1; write(data); };
  editor.onSubmit = () => { submissions++; };
  const stream = createViewStream(), replica = createViewReplica();
  const entries = Array.from({ length: 1000 }, (_, id) => entry(id, `History ${id}: 中文 evidence`));
  const advance = index => chat.update(replica.apply(JSON.parse(JSON.stringify(stream.next({ entries, docs: {
    'pi.live': { run: {}, generation: { message: { content: [{ type: 'text',
      text: 'Streaming 中文 **result**\n'.repeat(index) + `\nLatest ${index}` }] } } },
  } })))));
  advance(0); tui.start(); tui.renderNow(); await terminal.flush();
  bytes = 0; clears = 0;
  const durations = [];
  for (let index = 1; index <= 40; index++) {
    const start = performance.now();
    advance(index); terminal.sendInput('中a'); tui.renderNow(); await terminal.flush();
    durations.push(performance.now() - start);
  }
  assert.equal(editor.getText(), '中a'.repeat(40));
  assert.match(terminal.getViewport().join('\n'), /Latest 40/);
  assert.match(terminal.getViewport().join('\n'), /中a/);
  assert.equal(clears, 0, 'ordinary streaming and editing should use row updates');
  terminal.sendInput('\x1b[200~中文粘贴\nsecond line\x1b[201~');
  assert.match(editor.getExpandedText(), /中文粘贴\nsecond line/);
  assert.equal(submissions, 0);
  durations.sort((a, b) => a - b);
  await mkdir(TEST_ROOT, { recursive: true });
  await writeFile(join(TEST_ROOT, 'terminal-interactive-performance.json'), JSON.stringify({
    history_messages: entries.length, updates: durations.length, terminal_bytes: bytes, full_clears: clears,
    p50_ms: durations[20], p95_ms: durations[38], max_ms: durations.at(-1),
  }));
});
