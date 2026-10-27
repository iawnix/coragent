import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { createCacheDiagnostics, cacheUsage, cacheDiagnosticWriter } from '../../../apps/agent/context/cache-diagnostics.mjs';
import { requestCaptureWriter } from '../../../apps/agent/context/request-capture.mjs';
import { pinnedPiSource, TEST_ROOT } from './test-environment.mjs';

const { stream } = await import(pathToFileURL(join(pinnedPiSource(), 'packages/ai/src/api/openai-completions.ts')));
const model = { id:'fixture', provider:'fixture', api:'openai-completions', baseUrl:'http://127.0.0.1:1/v1',
  reasoning:false, input:['text'], contextWindow:200000, maxTokens:512,
  cost:{input:0,output:0,cacheRead:0,cacheWrite:0} };
const messages = () => [{role:'system',content:'private policy',timestamp:0},
  {role:'user',content:'private research '.repeat(500),timestamp:0}];
const models = { streamSimple:(m,c,o)=>stream(m,c,o) };

function sse(usage) {
  const chunks = [
    {choices:[{index:0,delta:{role:'assistant',content:'完成'},finish_reason:null}]},
    {choices:[{index:0,delta:{},finish_reason:'stop'}]},
    ...(usage ? [{choices:[],usage}] : []),
  ];
  const text = chunks.map(chunk=>`data: ${JSON.stringify(chunk)}\n\n`).join('')+'data: [DONE]\n\n';
  const bytes = new TextEncoder().encode(text);
  let offset=0;
  return new Response(new ReadableStream({pull(controller) {
    if(offset===bytes.length) return controller.close();
    controller.enqueue(bytes.slice(offset,offset+7));offset=Math.min(bytes.length,offset+7);
  }}),{headers:{'content-type':'text/event-stream'}});
}

test('real adapter diagnostics preserve payload and output, distinguish absent/zero/cache-hit usage', async () => {
  const records=[],bodies=[];
  const diagnostics=createCacheDiagnostics({write:row=>records.push(row)});
  const wrapped=diagnostics.wrap(models), history=messages();
  diagnostics.context('42',12);
  diagnostics.tag(history,{generation_id:'42',sources:[{producer:'job_manager',reason:'job_event'}]});
  const usages=[{prompt_tokens:100,completion_tokens:1},
    {prompt_tokens:100,completion_tokens:1,prompt_tokens_details:{cached_tokens:0}},
    {prompt_tokens:100,completion_tokens:1,prompt_tokens_details:{cached_tokens:80}}];
  for (const usage of usages) {
    const result=await wrapped.streamSimple(model,{messages:history},{apiKey:'fake-secret',maxTokens:32,maxRetries:0,
      onPayload(payload){payload.custom_fixture='unchanged';return payload;},
      fetch:async (_url,init)=>{bodies.push(init.body);return sse(usage);}}).result();
    assert.equal(result.stopReason,'stop');
    assert.equal(result.content.find(b=>b.type==='text').text,'完成');
    assert.equal(result.usage.cacheRead,usage.prompt_tokens_details?.cached_tokens??0);
  }
  assert.equal(new Set(bodies).size,1);
  assert.equal(JSON.parse(bodies[0]).custom_fixture,'unchanged');
  const replies=records.filter(r=>r.phase==='response');
  assert.deepEqual(replies.map(r=>r.usage.cache_read_status),['not_reported','reported','reported']);
  assert.deepEqual(replies.map(r=>r.usage.cache_hit_fraction),[null,0,0.8]);
  assert.equal(replies[0].prefix.input_identical,null);
  assert.equal(replies[1].prefix.input_identical,true);
  assert.equal(replies[1].prefix.common_prefix_bytes_lower_bound,replies[1].prefix.input_json_bytes);
  assert.equal(replies[2].generation_id,'42');assert.equal(replies[2].context_head_id,12);
  assert.deepEqual(replies[2].sources,[{producer:'job_manager',reason:'job_event'}]);
  assert.doesNotMatch(JSON.stringify(records),/fake-secret|private policy|private research|完成|custom_fixture/);
});

test('appending history preserves the measured prefix; early edits and tool changes are distinguishable', async () => {
  const records=[],diagnostics=createCacheDiagnostics({write:r=>records.push(r)}),wrapped=diagnostics.wrap(models);
  const history=messages();
  const run=async content=>wrapped.streamSimple(model,{messages:content},{apiKey:'fake',maxRetries:0,
    fetch:async()=>sse({prompt_tokens:9000,prompt_tokens_details:{cached_tokens:0}})}).result();
  await run(history);
  await run([...history,{role:'user',content:'Next step',timestamp:0}]);
  let row=records.at(-1);
  assert.equal(row.prefix.unchanged_leading_messages,2);
  assert.ok(row.prefix.common_prefix_bytes_lower_bound>=row.prefix.previous_input_json_bytes-1024);
  assert.equal(row.prefix.tools_unchanged,true);
  await run([{...history[0],content:'Changed policy'},history[1]]);
  assert.equal(records.at(-1).prefix.unchanged_leading_messages,0);
  assert.equal(records.at(-1).prefix.common_prefix_bytes_lower_bound,0);
  await run([{...history[0],content:'Changed policy',toolsAdded:[{name:'fixture_tool',description:'test',parameters:{type:'object',properties:{}}}]},history[1]]);
  assert.equal(records.at(-1).prefix.tools_unchanged,false);
});

test('summary calls have separate prefix comparisons and failures never leak error text', async () => {
  const records=[],diagnostics=createCacheDiagnostics({write:r=>records.push(r)}),wrapped=diagnostics.wrap(models);
  const opts={apiKey:'fake',maxRetries:0,fetch:async()=>sse({prompt_tokens:100,prompt_tokens_details:{cached_tokens:50}})};
  await wrapped.streamSimple(model,{messages:messages()},opts).result();
  await wrapped.completeSimple(model,{messages:messages()},opts);
  assert.equal(records.at(-1).purpose,'auxiliary');
  assert.equal(records.at(-1).prefix.previous_input_json_bytes,null);
  await wrapped.streamSimple(model,{messages:messages()},{...opts,fetch:async()=>{throw Error('private transport details');}}).result();
  assert.equal(records.at(-1).outcome,'transport_error');
  assert.equal(records.at(-1).usage,null);
  assert.doesNotMatch(JSON.stringify(records),/private transport details/);
  const broken=createCacheDiagnostics({write:async()=>{throw Error('disk unavailable');}}).wrap(models);
  assert.equal((await broken.completeSimple(model,{messages:messages()},opts)).stopReason,'stop');
});

test('HTTP retries remain separate attempts and observe raw Responses usage without altering bytes', async () => {
  const records=[];
  const diagnostics=createCacheDiagnostics({write:r=>records.push(r)});
  const wrapped=diagnostics.wrap({streamSimple:(_m,_c,options)=>options});
  const body='data: '+JSON.stringify({type:'response.completed',response:{usage:{input_tokens:100,output_tokens:2,input_tokens_details:{cached_tokens:90}}}})+'\n\n';
  const options=wrapped.streamSimple({...model,api:'openai-responses'},{messages:[]},{fetch:async()=>new Response(body,{headers:{'content-type':'text/event-stream'}})});
  for(let i=0;i<2;i++) {
    const response=await options.fetch('http://127.0.0.1:1',{body:JSON.stringify({input:[{role:'user',content:'synthetic'}]})});
    assert.equal(await response.text(),body);
  }
  const replies=records.filter(r=>r.phase==='response');
  assert.deepEqual(replies.map(r=>r.attempt),[1,2]);
  assert.equal(replies[0].request_id,replies[1].request_id);
  assert.equal(replies[0].usage.cache_hit_fraction,0.9);
  assert.equal(cacheUsage({input_tokens:100,input_tokens_details:{cached_tokens:200}},'openai-responses').cache_hit_fraction,null);
});

test('non-SSE, cancelled and broken streams report unknown usage rather than zero cache hits', async () => {
  const records=[],diagnostics=createCacheDiagnostics({write:r=>records.push(r)});
  const wrapped=diagnostics.wrap({streamSimple:(_m,_c,o)=>o});
  const cases=[()=>new Response('private error',{status:429}),
    ()=>new Response(new ReadableStream({pull(c){c.error(Error('private stream failure'));}}),{headers:{'content-type':'text/event-stream'}}),
    ()=>new Response(new ReadableStream({}),{headers:{'content-type':'text/event-stream'}})];
  for(let i=0;i<cases.length;i++) {
    const opts=wrapped.streamSimple(model,{messages:[]},{fetch:async()=>cases[i]()});
    const response=await opts.fetch('http://127.0.0.1:1',{body:'{}'});
    if(i===0)assert.equal(await response.text(),'private error');
    if(i===1)await assert.rejects(response.text(),/private stream failure/);
    if(i===2)await response.body.cancel();
  }
  const replies=records.filter(r=>r.phase==='response');
  assert.deepEqual(replies.map(r=>r.outcome),['unobserved_response','stream_error','stream_cancelled']);
  assert.ok(replies.every(r=>r.cache_read_status==='not_reported'));
  assert.doesNotMatch(JSON.stringify(records),/private error|private stream failure/);
});

test('diagnostic files rotate locally and flush before shutdown', async t => {
  const root=await mkdtemp(join(TEST_ROOT,'cache-diagnostic-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const file=join(root,'request-cache.jsonl');
  await writeFile(file,'x'.repeat(8*1024*1024),{mode:0o600});
  const log=cacheDiagnosticWriter(file);
  log.write({fixture:1});log.write({fixture:2});await log.flush();
  assert.deepEqual((await readFile(file,'utf8')).trim().split('\n').map(JSON.parse),[{fixture:1},{fixture:2}]);
  assert.equal((await stat(`${file}.1`)).size,8*1024*1024);
  assert.equal((await stat(file)).mode&0o777,0o600);
});

test('opt-in request capture preserves wire bodies before fetch, separates retries, and omits transport credentials', async t => {
  const root=await mkdtemp(join(TEST_ROOT,'request-capture-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const directory=join(root,'request-bodies'), records=[];
  const captureRequest=requestCaptureWriter(directory,{sessionId:'fixture-session',workspaceId:'fixture-workspace'});
  const wrapped=createCacheDiagnostics({write:r=>records.push(r),captureRequest}).wrap({streamSimple:(_m,_c,o)=>o});
  const body=' { "model": "fixture", "messages": [{"role":"user","content":"private research"}], "tools": [] } ';
  const options=wrapped.streamSimple(model,{messages:[]},{fetch:async (_url,init)=>{
    assert.equal(init.body,body);
    assert.equal(new Headers(init.headers).get('authorization'),'Bearer fixture-secret');
    const row=records.at(-1);
    assert.equal(row.request_capture.status,'saved');
    const saved=JSON.parse(gunzipSync(await readFile(join(directory,row.request_capture.file))));
    assert.equal(saved.body,body);
    assert.equal(saved.session_id,'fixture-session');
    assert.equal(saved.workspace_id,'fixture-workspace');
    assert.equal(saved.headers.session_id,'fixture-affinity');
    assert.equal(saved.endpoint,'https://fixture.invalid/v1/chat/completions');
    assert.doesNotMatch(JSON.stringify(saved),/fixture-secret|fixture-cookie|url-secret|query-secret|custom-secret/);
    return sse({prompt_tokens:100,prompt_tokens_details:{cached_tokens:80}});
  }});
  for(let i=0;i<2;i++) {
    const response=await options.fetch('https://user:url-secret@fixture.invalid/v1/chat/completions?key=query-secret',{
      method:'POST',body,headers:{authorization:'Bearer fixture-secret',cookie:'fixture-cookie',
        'x-custom-token':'custom-secret',session_id:'fixture-affinity','content-type':'application/json'},
    });
    await response.text();
  }
  const replies=records.filter(r=>r.phase==='response');
  assert.equal(replies.length,2);
  assert.deepEqual(replies.map(r=>r.attempt),[1,2]);
  assert.notEqual(replies[0].request_capture.file,replies[1].request_capture.file);
  assert.equal((await readdir(directory)).length,2);
  assert.equal((await stat(directory)).mode&0o777,0o700);
  for(const row of replies) assert.equal((await stat(join(directory,row.request_capture.file))).mode&0o777,0o600);
  assert.doesNotMatch(JSON.stringify(records),/private research|fixture-secret/);
});

test('capture failures are visible without breaking requests or leaking errors; disabled capture stays absent', async t => {
  const root=await mkdtemp(join(TEST_ROOT,'request-capture-failure-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const blocker=join(root,'blocked');await writeFile(blocker,'fixture');
  const diskFailure=requestCaptureWriter(join(blocker,'child'));
  for(const captureRequest of [undefined,diskFailure,async()=>{throw Error('private error');}]) {
    const records=[];
    const wrapped=createCacheDiagnostics({write:r=>records.push(r),captureRequest}).wrap({streamSimple:(_m,_c,o)=>o});
    const opts=wrapped.streamSimple(model,{messages:[]},{fetch:async()=>sse({prompt_tokens:10})});
    const response=await opts.fetch('https://fixture.invalid',{body:'{}'});
    await response.text();
    const row=records.at(-1);
    if(captureRequest) assert.equal(row.request_capture.status,'error');
    else assert.equal(Object.hasOwn(row,'request_capture'),false);
    assert.equal(row.http_status,200);
    assert.doesNotMatch(JSON.stringify(records),/private error/);
  }
});
