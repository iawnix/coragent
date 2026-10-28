import assert from 'node:assert/strict';
import test from 'node:test';
import {setImmediate} from 'node:timers/promises';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {Harness, MemoryStorage, createRegistry, defineExtension, hook, GenerationTask, CompactionTask, LiveDoc} from '@earendil-works/pi-durable';
import {createModels, fauxProvider, fauxAssistantMessage} from '@earendil-works/pi-ai';
import {TODO_CONTEXT as context} from '@earendil-works/chord/context';
import {pinnedPiSource} from './test-environment.mjs';

const source = path => import(pathToFileURL(join(pinnedPiSource(),path)));
const {createCompaction} = await source('packages/durable/src/harness/compaction.ts');
import {compactionOutcome} from '../../../apps/agent/runtime/compaction.mjs';
const deferred = () => Promise.withResolvers();

async function until(predicate, diagnose = () => null) {
  for (let i=0;i<10000;i++) {
    if (await predicate()) return;
    await setImmediate();
  }
  assert.fail('Durable task did not reach the expected state: '+JSON.stringify(await diagnose()));
}

async function fixture(t,{generationHooks={},compactionHooks={}}={}) {
  const faux=fauxProvider({models:[{id:'faux-1',contextWindow:20000,maxTokens:128}]});
  const models=createModels();models.setProvider(faux.provider);
  const registry=createRegistry();
  registry.install(defineExtension({name:'compact-coordination',hooks:[
    hook(GenerationTask,generationHooks),hook(CompactionTask,compactionHooks),
  ]}));
  const settings={compaction:{enabled:false,keepRecentTokens:0,maxInputTokens:500,backgroundTokens:100},retry:{enabled:false}};
  const harness=await Harness.open(new MemoryStorage(),{models,registry,settings},context);
  const cleanup=[];
  t.after(async()=>{for(const release of cleanup)release();await harness.close(context);});
  const conversation=await harness.root(context,{agent:{model:{provider:'faux',modelId:'faux-1'}}});
  const state={summaries:[],generations:[],summary:async()=>fauxAssistantMessage('Preserved history.'),answer:async()=>fauxAssistantMessage('Continued')};
  faux.setResponses(Array.from({length:20},()=>async (request,options)=>{
    const summary=options?.cacheRetention==='none';
    state[summary?'summaries':'generations'].push({request,options});
    return state[summary?'summary':'answer'](request,options);
  }));
  for (const [kind,message] of [
    ['pi.user',{role:'user',content:'Historical input '.repeat(700),timestamp:0}],
    ['pi.assistant',fauxAssistantMessage('Historical answer')],
  ]) await conversation.submit({type:'write',entry:{kind,model:[message]}},context);
  return {harness,conversation,settings,state,cleanup:fn=>cleanup.push(fn),outcome:id=>compactionOutcome(harness,conversation,id,context,{wait:true}),
    background:async()=>{const id=await conversation.commit(tx=>createCompaction(tx,conversation.id,{reason:'threshold'}),context);harness.resume();return id;}};
}

for (const trigger of ['threshold','admission','provider-overflow']) {
  test(`manual and ${trigger} compaction join an active background summary`,{timeout:10000},async t=>{
    let block=true;
    const f=await fixture(t,{generationHooks:{beforeRequest(){
      if (trigger==='admission' && block) {block=false;return {block:'Input budget exceeded',compact:true};}
    }}});
    const entered=deferred(),release=deferred();
    f.cleanup(()=>release.resolve());
    f.state.summary=async()=>{entered.resolve();await release.promise;return fauxAssistantMessage('Shared summary.');};
    if (trigger==='provider-overflow') f.state.answer=async()=>f.state.generations.length===1
      ? fauxAssistantMessage('',{stopReason:'error',errorMessage:'maximum context length exceeded'})
      : fauxAssistantMessage('Recovered');
    const id=await f.background();await entered.promise;
    assert.equal(await f.conversation.compact(undefined,context),id);
    assert.equal(await f.conversation.compact(undefined,context),id);
    if (trigger!=='admission') f.settings.compaction.enabled=true;
    if (trigger==='provider-overflow') f.settings.compaction.maxInputTokens=19000;
    const submission=await f.conversation.submit({type:'input',content:'Continue'},context);
    await until(async()=>{
      const live=await f.harness.snapshot(LiveDoc,f.conversation.id,context);
      const run=live?.run && await f.harness.getTask(live.run.taskId,context);
      return run?.state.status==='waiting' && run.state.on.includes(id);
    }, async()=>({submission:await submission.status(context),live:await f.harness.snapshot(LiveDoc,f.conversation.id,context)}));
    release.resolve();
    assert.equal((await submission.wait(context)).status,'done');
    assert.equal((await f.outcome(id)).status,'completed');
    assert.equal(f.state.summaries.length,1);
    assert.equal(f.state.generations.length,trigger==='provider-overflow'?2:1);
    assert.match(JSON.stringify(f.state.generations.at(-1).request.messages),/Shared summary/);
    assert.equal(f.state.summaries[0].options.sessionId,f.state.generations.at(-1).options.sessionId);
    const entries=await f.conversation.entries({},100,undefined,context);
    assert.equal(entries.items.filter(entry=>entry.kind==='pi.compaction').length,1);
  });
}

test('a finished but queued summary is reused and placed before a blocked generation resumes',{timeout:10000},async t=>{
  const requestEntered=deferred(),requestRelease=deferred();let first=true;
  const f=await fixture(t,{generationHooks:{async beforeRequest(){
    if (first) {first=false;requestEntered.resolve();await requestRelease.promise;return {block:'Budget full',compact:true};}
  }}});
  f.cleanup(()=>requestRelease.resolve());
  const submission=await f.conversation.submit({type:'input',content:'Continue'},context);await requestEntered.promise;
  const id=await f.background();
  const task=await f.harness.waitForTask(id,context);
  const write=await f.harness.submission(task.state.outcome.result.submissionId,context);
  assert.equal((await write.status(context)).status,'queued');
  assert.equal(await f.conversation.compact(undefined,context),id);
  await assert.rejects(f.conversation.compact('Different focus',context),/different instructions/);
  requestRelease.resolve();
  assert.equal((await submission.wait(context)).status,'done');
  assert.equal((await write.status(context)).status,'done');
  assert.equal(f.state.summaries.length,1);
});

test('concurrent manual requests preserve their instructions and use one summary',{timeout:10000},async t=>{
  const f=await fixture(t),entered=deferred(),release=deferred();
  f.cleanup(()=>release.resolve());
  f.state.summary=async request=>{entered.resolve();await release.promise;assert.match(JSON.stringify(request.messages),/Focus on constraints/);return fauxAssistantMessage('Constraints preserved');};
  const first=await f.conversation.compact('Focus on constraints',context);await entered.promise;
  const repeated=await Promise.all(Array.from({length:8},()=>f.conversation.compact('Focus on constraints',context)));
  assert.ok(repeated.every(id=>id===first));
  await assert.rejects(f.conversation.compact('Focus on results',context),/different instructions/);
  release.resolve();
  assert.equal((await f.outcome(first)).status,'completed');
  assert.equal(f.state.summaries.length,1);
});

test('a native background threshold and manual request share a summary while generation continues',{timeout:10000},async t=>{
  const f=await fixture(t),summaryEntered=deferred(),answerEntered=deferred(),release=deferred();
  f.cleanup(()=>release.resolve());
  f.settings.compaction.enabled=true;
  f.settings.compaction.maxInputTokens=10000;
  f.settings.compaction.backgroundTokens=9000;
  f.state.summary=async()=>{summaryEntered.resolve();await release.promise;return fauxAssistantMessage('Native background summary');};
  f.state.answer=async()=>{answerEntered.resolve();await release.promise;return fauxAssistantMessage('Answer');};
  const submission=await f.conversation.submit({type:'input',content:'Continue'},context);
  await Promise.all([summaryEntered.promise,answerEntered.promise]);
  const live=await f.harness.snapshot(LiveDoc,f.conversation.id,context);
  assert.equal(live.compactions.length,1);
  assert.equal(await f.conversation.compact(undefined,context),live.compactions[0].taskId);
  release.resolve();
  assert.equal((await submission.wait(context)).status,'done');
  assert.equal((await f.outcome(live.compactions[0].taskId)).status,'completed');
  assert.equal(f.state.summaries.length,1);
});

test('cancelling a shared summary settles the waiting generation without a second request',{timeout:10000},async t=>{
  const f=await fixture(t),entered=deferred();
  f.state.summary=async(_request,options)=>{
    entered.resolve();
    await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true}));
    return fauxAssistantMessage('Unused');
  };
  const id=await f.background();await entered.promise;
  assert.equal(await f.conversation.compact(undefined,context),id);
  f.settings.compaction.enabled=true;
  const submission=await f.conversation.submit({type:'input',content:'Continue'},context);
  await until(async()=>{
    const live=await f.harness.snapshot(LiveDoc,f.conversation.id,context);
    return live?.run && (await f.harness.getTask(live.run.taskId,context))?.state.status==='waiting';
  });
  await f.conversation.abort(context,{background:true});
  assert.equal((await submission.wait(context)).reason,'aborted');
  assert.equal((await f.outcome(id)).status,'cancelled');
  assert.equal(f.state.summaries.length,1);
  assert.equal(f.state.generations.length,0);
});

for (const scenario of ['failed','declined']) {
  test(`a ${scenario} blocking compaction stops before the main provider request`,{timeout:10000},async t=>{
    const f=await fixture(t,{compactionHooks:scenario==='declined'?{beforeCompact:()=>({decline:true})}:{}});
    f.settings.compaction.enabled=true;
    f.state.summary=async()=>fauxAssistantMessage('',{stopReason:'error',errorMessage:'Summary unavailable'});
    const result=await (await f.conversation.submit({type:'input',content:'Continue'},context)).wait(context);
    assert.equal(result.status,'unanswered');
    assert.match(result.detail,/Compaction failed/);
    assert.equal(f.state.generations.length,0);
  });
}

test('a reset queued while waiting on a shared summary wins without reviving old history',{timeout:10000},async t=>{
  const f=await fixture(t),entered=deferred(),release=deferred();
  f.cleanup(()=>release.resolve());
  f.state.summary=async()=>{entered.resolve();await release.promise;return fauxAssistantMessage('Obsolete summary');};
  const id=await f.background();await entered.promise;
  f.settings.compaction.enabled=true;
  const original=await f.conversation.submit({type:'input',content:'Old continuation'},context);
  await until(async()=>{
    const live=await f.harness.snapshot(LiveDoc,f.conversation.id,context);
    return live?.run && (await f.harness.getTask(live.run.taskId,context))?.state.status==='waiting';
  });
  await f.conversation.reset('New context',context);
  const next=await f.conversation.submit({type:'input',content:'New input',whenBusy:'steer'},context);
  release.resolve();
  assert.equal((await original.wait(context)).reason,'reset');
  assert.equal((await next.wait(context)).status,'done');
  const compacted=await f.harness.waitForTask(id,context);
  const write=await f.harness.submission(compacted.state.outcome.result.submissionId,context);
  assert.equal((await write.status(context)).reason,'stale');
  assert.doesNotMatch(JSON.stringify(f.state.generations.at(-1).request.messages),/Historical input|Obsolete summary/);
  assert.equal(f.state.summaries.length,1);
});
