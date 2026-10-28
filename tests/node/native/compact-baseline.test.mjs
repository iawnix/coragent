import assert from 'node:assert/strict';
import test from 'node:test';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {Harness,MemoryStorage,createRegistry} from '@earendil-works/pi-durable';
import {createModels,fauxAssistantMessage} from '@earendil-works/pi-ai';
import {TODO_CONTEXT as context} from '@earendil-works/chord/context';
import {pinnedPiSource} from './test-environment.mjs';

const {readContextFrom}=await import(pathToFileURL(join(pinnedPiSource(),'packages/durable/src/harness/context.ts')));

test('post-compact baseline leads retained assistant history in full and incremental context reads',async t=>{
  // Pi #10904: a retained assistant used to prevent the new baseline from leading the request.
  const storage=new MemoryStorage();
  const harness=await Harness.open(storage,{models:createModels(),registry:createRegistry()},context);
  t.after(()=>harness.close(context));
  const conversation=await harness.root(context);
  const append=entry=>conversation.commit(tx=>tx.appendEntry(conversation.id,entry),context);
  const kept=await append({kind:'pi.assistant',model:[fauxAssistantMessage('Retained assistant')]});
  await append({kind:'pi.compaction',head:kept.id,model:[{role:'user',content:'Summary',timestamp:0}]});
  let cached=await readContextFrom(harness,storage,conversation.id,context,undefined,undefined);
  assert.deepEqual(cached.view.messages.map(message=>message.role),['user','assistant']);
  const baseline=await append({kind:'pi.system',model:[{role:'system',content:'Baseline',timestamp:0}]});
  cached=await readContextFrom(harness,storage,conversation.id,context,undefined,cached.range);
  assert.deepEqual(cached.view.messages.map(message=>message.role),['system','user','assistant']);
  assert.deepEqual(cached.view.messages,(await conversation.context(context)).messages);
  await append({kind:'pi.system',model:[{role:'system',content:'Later update',timestamp:0}]});
  cached=await readContextFrom(harness,storage,conversation.id,context,undefined,cached.range);
  assert.equal(cached.view.messages[0].content,'Baseline');
  assert.equal(cached.view.messages.at(-1).content,'Later update');
  assert.deepEqual(cached.view.messages,(await conversation.context(context)).messages);
  await append({kind:'edit',edits:[{target:baseline.id,action:'omit'}]});
  cached=await readContextFrom(harness,storage,conversation.id,context,undefined,cached.range);
  assert.deepEqual(cached.view.messages.map(message=>message.role),['user','assistant','system']);
  assert.equal(cached.view.messages.at(-1).content,'Later update');
  assert.deepEqual(cached.view.messages,(await conversation.context(context)).messages);
});
