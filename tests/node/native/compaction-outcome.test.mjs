import assert from 'node:assert/strict';
import test from 'node:test';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {Harness,MemoryStorage,createRegistry,defineExtension,hook,CompactionTask} from '@earendil-works/pi-durable';
import {createModels,fauxProvider,fauxAssistantMessage} from '@earendil-works/pi-ai';
import {TODO_CONTEXT as context} from '@earendil-works/chord/context';
import {pinnedPiSource} from './test-environment.mjs';
const fromSource = path => import(pathToFileURL(join(pinnedPiSource(),path)));
import {compactionOutcome} from '../../../apps/agent/runtime/compaction.mjs';
import {createChatView} from '../../../apps/agent/terminal/chat.mjs';

for (const scenario of ['completed','skipped','failed','cancelled']) {
  test(`manual compaction reports ${scenario} from its durable operation`, {timeout:10000}, async t => {
    const faux = fauxProvider(); const models = createModels(); models.setProvider(faux.provider);
    const registry = createRegistry();
    let started, release;
    const pending = new Promise(resolve => { started = resolve; });
    if (scenario === 'completed' || scenario === 'cancelled') registry.install(defineExtension({name:'compact-outcome',hooks:[
      hook(CompactionTask,{async beforeCompact(){
        if (scenario === 'cancelled') { started(); await new Promise(resolve => {release=resolve;}); }
        return {summary:'PRIVATE SUMMARY CONTENT'};
      }}),
    ]}));
    const harness = await Harness.open(new MemoryStorage(),{models,registry,
      settings:{compaction:{enabled:false,keepRecentTokens:0},retry:{enabled:false}}},context);
    t.after(()=>harness.close(context));
    const conversation = await harness.root(context,{agent:{model:{provider:'faux',modelId:'faux-1'}}});
    if (scenario !== 'skipped') {
      faux.setResponses([fauxAssistantMessage('Answer'),fauxAssistantMessage('',{stopReason:'error',errorMessage:'Summary provider unavailable'})]);
      await (await conversation.submit({type:'input',content:'History '.repeat(100)},context)).wait(context);
    }
    const operationId = await conversation.compact(undefined,context);
    if (scenario === 'cancelled') {
      await pending;
      const aborting = conversation.abort(context,{background:true});
      release();
      await aborting;
    }
    const outcome = await compactionOutcome(harness,conversation,operationId,context,{wait:true});
    assert.equal(outcome.status,scenario);
    if (scenario === 'failed') assert.match(outcome.error,/Summary provider unavailable/);
    if (scenario === 'completed') {
      // Completion means the summary has actually been placed, including queued placement.
      const entries = await conversation.entries({},100,undefined,context);
      assert.ok(entries.items.some(entry => entry.kind === 'pi.compaction'));
      const [components,themes] = await Promise.all([
        fromSource('packages/tui/src/index.ts'),
        fromSource('packages/coding-agent/src/modes/interactive/theme/theme.ts'),
      ]);
      themes.initTheme('dark');
      const chat = createChatView({components,theme:themes.theme,markdownTheme:themes.getMarkdownTheme(),requestRender(){}});
      const state = await conversation.viewState(context);
      try {
        chat.update(state.value);
        const rendered = chat.render(100).join('\n');
        assert.match(rendered,/Context compacted/);
        assert.doesNotMatch(rendered,/PRIVATE SUMMARY CONTENT/);
      } finally {await state.dispose(context);}
    }
    await assert.rejects(compactionOutcome(harness,conversation,'invalid',context),/Unknown compaction/);
    const other = await harness.createConversation({ownership:{kind:'ownerless'}},context);
    await assert.rejects(compactionOutcome(harness,other,operationId,context),/Unknown compaction/);
  });
}
