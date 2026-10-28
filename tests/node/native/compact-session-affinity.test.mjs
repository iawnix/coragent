import assert from 'node:assert/strict';
import test from 'node:test';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {pinnedPiSource} from './test-environment.mjs';

const {stream}=await import(pathToFileURL(join(pinnedPiSource(),'packages/ai/src/api/openai-completions.ts')));
const model={id:'local-fixture',name:'Local fixture',provider:'fixture',api:'openai-completions',
  baseUrl:'https://fixture.invalid/v1',input:['text'],reasoning:false,contextWindow:20000,maxTokens:128,
  cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};

async function capture(compat,options={}) {
  let sent;
  const response=await stream({...model,compat},{messages:[{role:'user',content:'Synthetic summary',timestamp:0}]},{
    apiKey:'fake-key',sessionId:'same-conversation',cacheRetention:'none',maxRetries:0,...options,
    fetch:async(url,init)=>{
      sent={url,headers:new Headers(init.headers),body:JSON.parse(init.body)};
      return new Response('data: {"id":"fixture","choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        {headers:{'content-type':'text/event-stream'}});
    },
  }).result();
  assert.equal(response.stopReason,'stop',response.errorMessage);
  return sent;
}

test('summary cache opt-out retains opted-in routing headers without enabling prompt cache fields',async()=>{
  const summary=await capture({sendSessionAffinityHeaders:true,supportsLongCacheRetention:true});
  const normal=await capture({sendSessionAffinityHeaders:true},{cacheRetention:'short'});
  for (const name of ['session_id','x-client-request-id','x-session-affinity']) {
    assert.equal(summary.headers.get(name),'same-conversation');
    assert.equal(summary.headers.get(name),normal.headers.get(name));
  }
  assert.equal(summary.body.prompt_cache_key,undefined);
  assert.equal(summary.body.prompt_cache_retention,undefined);
});

test('affinity opt-out, provider header format, and explicit overrides remain effective',async()=>{
  const disabled=await capture({sendSessionAffinityHeaders:false});
  assert.equal(disabled.headers.get('x-session-affinity'),null);
  const router=await capture({sendSessionAffinityHeaders:true,sessionAffinityFormat:'openrouter'});
  assert.equal(router.headers.get('x-session-id'),'same-conversation');
  assert.equal(router.headers.get('session_id'),null);
  const override=await capture({sendSessionAffinityHeaders:true},{headers:{'x-session-affinity':'explicit'}});
  assert.equal(override.headers.get('x-session-affinity'),'explicit');
});
