import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdir, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { stripVTControlCharacters } from 'node:util';
import { pinnedPiSource, TEST_ROOT } from './test-environment.mjs';
import { createChatView } from '../../../apps/agent/terminal/chat.mjs';
import { createWorkingStatus, workingLabel } from '../../../apps/agent/terminal/status/working.mjs';
import { createViewStream, createViewReplica } from '../../../apps/agent/transport/view-stream.mjs';
import { createRefreshLoop } from '../../../apps/agent/terminal/commands/facet.mjs';

const source = pinnedPiSource();
const components = await import(pathToFileURL(join(source,'packages/tui/src/index.ts')));
const themes = await import(pathToFileURL(join(source,'packages/coding-agent/src/modes/interactive/theme/theme.ts')));
themes.initTheme('dark');
const wire = value => JSON.parse(JSON.stringify(value));

test('1000-message history is not rendered again for tokens, animation frames or editor redraws', async () => {
  let constructions=0, renders=0;
  class Markdown extends components.Markdown {
    constructor(...args) { super(...args); constructions++; }
    render(width) { renders++; return super.render(width); }
  }
  const chat=createChatView({components:{...components,Markdown},theme:themes.theme,markdownTheme:themes.getMarkdownTheme(),requestRender(){}});
  const stream=createViewStream(), replica=createViewReplica();
  const entries=Array.from({length:1000},(_,id)=>({id,kind:'pi.assistant',model:[{role:'assistant',content:[{type:'text',text:`History ${id}: **measurement**\n\n- result\n- evidence`}]}]}));
  const next=text=>({entries,docs:{'pi.live':{run:{taskId:1},tools:[],generation:{message:{content:[{type:'text',text}]}}}}});
  const advance=value=>chat.update(replica.apply(wire(stream.next(value))));
  advance(next('Start')); chat.render(100);
  const initialConstructions=constructions,initialRenders=renders;
  const durations=[];
  for(let i=1;i<=60;i++) {
    const start=performance.now(); advance(next('Streaming 中文 **result** '.repeat(i)));
    const lines=chat.render(100); durations.push(performance.now()-start);
    for(let frame=0;frame<4;frame++) assert.equal(chat.render(100),lines);
  }
  assert.equal(constructions,initialConstructions,'streaming Markdown keeps its identity');
  assert.equal(renders-initialRenders,60,'only the changing message needs layout');
  assert.match(chat.render(100).join('\n'),/History 999/);
  assert.match(chat.render(100).join('\n'),/Streaming 中文/);
  const toolEntry={id:1000,kind:'pi.assistant',model:[{role:'assistant',stopReason:'toolUse',content:[{type:'toolCall',id:'tool-1',name:'bash',arguments:{command:'echo fixture'}}]}]};
  const toolEntries=[...entries,toolEntry];
  const tools=output=>({entries:toolEntries,docs:{'pi.live':{run:{taskId:1},tools:[{callId:'tool-1',name:'bash',status:'running',output}]}}});
  advance(tools('first')); chat.render(100);
  const beforeTools=renders;
  for(let i=1;i<=20;i++) { advance(tools(`progress ${i}`)); chat.render(100); }
  assert.equal(renders,beforeTools,'tool output changes must not re-render historical Markdown');
  const narrow=chat.render(20); assert.ok(narrow.length>chat.render(100).length);
  const compacted={entries:[{id:1001,kind:'pi.compaction',model:[]}],docs:{}};
  advance(compacted); assert.doesNotMatch(chat.render(100).join('\n'),/History 999|Streaming/);
  assert.match(chat.render(100).join('\n'),/Context compacted/);
  durations.sort((a,b)=>a-b);
  await mkdir(TEST_ROOT,{recursive:true});
  await writeFile(join(TEST_ROOT,'terminal-streaming-performance.json'),JSON.stringify({history_messages:entries.length,updates:durations.length,p50_ms:durations[30],p95_ms:durations[57],max_ms:durations.at(-1),history_rerenders_during_stream:0}));
  assert.ok(durations[57]<50,'synthetic stream update exceeds the local responsiveness budget');
});

test('work animation advances without tokens and stops on idle, panel hiding and disposal',t=>{
  t.mock.timers.enable({apis:['setInterval']});
  let requests=0;
  const status=createWorkingStatus({...components,theme:themes.theme,requestRender(){requests++;},animated:true,
    fallback:{render:()=>['Idle'],invalidate(){}}});
  t.after(()=>status.dispose());
  status.update({docs:{'pi.live':{run:{}}}}); status.setActive(true);
  const first=status.render(100); assert.equal(first.length,1); assert.match(stripVTControlCharacters(first[0]),/Working/);
  t.mock.timers.tick(80); assert.notDeepEqual(status.render(100),first);
  status.update({docs:{'pi.live':{run:{},tools:[{name:'bash',status:'running'}]}}});
  assert.match(stripVTControlCharacters(status.render(100)[0]),/Running bash/);
  status.setActive(false); const hidden=requests; t.mock.timers.tick(800); assert.equal(requests,hidden);
  status.setActive(true); t.mock.timers.tick(80); assert.ok(requests>hidden);
  status.update({docs:{}}); assert.deepEqual(status.render(100),['Idle']);
  const idle=requests; t.mock.timers.tick(800); assert.equal(requests,idle);
  status.update({docs:{'pi.live':{run:{}}}}); status.dispose();
  const disposed=requests; t.mock.timers.tick(800); assert.equal(requests,disposed);
  assert.match(workingLabel({docs:{'pi.live':{compactions:[{}]}}}),/Compacting/);
  assert.match(workingLabel({docs:{'pi.live':{generation:{retry:{},attempt:2}}}}),/attempt 3/);
});

test('hidden research polling makes no reads and identical responses do not repaint',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let enabled=false,reads=0,paints=0,fail=false;
  const loop=createRefreshLoop({enabled:()=>enabled,read:async()=>{reads++;if(fail)throw Error('fixture');return {value:'unchanged'};},
    apply(){paints++;},onError(){},intervalMs:100});
  t.after(()=>loop.stop());
  await loop.refresh(); assert.equal(reads,0);
  enabled=true; await loop.refresh(); assert.equal(reads,1); assert.equal(paints,1);
  await loop.refresh(); assert.equal(reads,2); assert.equal(paints,1);
  fail=true; await loop.refresh(); fail=false; await loop.refresh(); assert.equal(paints,2);
  enabled=false; t.mock.timers.tick(100); await new Promise(resolve=>setImmediate(resolve)); assert.equal(reads,4);
});
