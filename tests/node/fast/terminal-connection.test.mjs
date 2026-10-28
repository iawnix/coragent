import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';
import { subscribeSession } from '../../../apps/agent/terminal/connection.mjs';
import { createViewStream, createViewReplica } from '../../../apps/agent/transport/view-stream.mjs';

const until = async predicate => { for (let i=0;i<100;i++) { if (predicate()) return; await delay(5); } assert.fail('connection did not settle'); };
const entry = id => ({id,kind:'pi.user',model:[{role:'user',content:`entry ${id}`} ]});
const view = (text, entries = []) => ({ conversation:{id:1}, entries, docs:{'pi.live':{run:{taskId:1},tools:[],generation:{message:{content:[{type:'text',text}]}}}} });
const wire = value => JSON.parse(JSON.stringify(value));
function peer(initial) {
  const stream = createViewStream();
  return Object.assign(new EventEmitter(), { closed:false, requests:[],
    async request(method, params) {
      this.requests.push(method); assert.equal(method,'session/attach'); assert.equal(params.view_stream,true);
      return {frame:wire(stream.next(initial))};
    },
    close() { if (!this.closed) { this.closed=true; this.emit('close',new Error('fixture disconnect')); } },
    notify(value) { const frame=stream.next(value); if (frame) this.emit('notification',{method:'session/view',params:{workspace_id:'work',session_id:'session',frame:wire(frame)}}); },
  });
}
const subscribe = (connection, views, options={}) => subscribeSession({connect:async()=>connection,workspaceId:'work',sessionId:'session',onView:value=>views.push(value),onError:assert.fail,...options});

test('streamed tokens require no refresh RPC and retain unchanged history and tool identities',async t=>{
  const entries=Array.from({length:1000},(_,i)=>entry(i));
  const connection=peer(view('',entries)),views=[];
  const stop=subscribe(connection,views); t.after(stop); await until(()=>views.length===1);
  const history=views[0].entries,tools=views[0].docs['pi.live'].tools;
  for(let i=1;i<=40;i++) connection.notify(view('token '.repeat(i),entries));
  assert.equal(views.length,41);
  assert.deepEqual(connection.requests,['session/attach']);
  assert.equal(views.at(-1).entries,history); assert.equal(views.at(-1).docs['pi.live'].tools,tools);
  assert.equal(views.at(-1).docs['pi.live'].generation.message.content[0].text,'token '.repeat(40));
});

test('view deltas recover append, edits, compaction, removed documents and failures without resending history',()=>{
  const producer=createViewStream(),replica=createViewReplica();
  const entries=Array.from({length:1000},(_,i)=>entry(i));
  const initial=view('',entries),snapshot=wire(producer.next(initial)); replica.apply(snapshot);
  const next=view('new token',entries),frame=wire(producer.next(next));
  assert.ok(JSON.stringify(frame).length < JSON.stringify(snapshot).length / 50);
  assert.equal(frame.entries,undefined); assert.deepEqual(replica.apply(frame),{...next,failure:null});
  assert.equal(replica.apply(frame),null);
  const appended={...next,entries:[...entries,entry(1000)]};
  const appendFrame=wire(producer.next(appended)); assert.equal(appendFrame.entries.items.length,1);
  assert.deepEqual(replica.apply(appendFrame),{...appended,failure:null});
  const edited={...appended,entries:[entry('edited'),...appended.entries.slice(1)]};
  assert.deepEqual(replica.apply(wire(producer.next(edited))),{...edited,failure:null});
  const compacted={conversation:{id:1},entries:[entry('compaction'),entry(1000)],docs:{},failure:{summary:'Blocked',detail:'fixture'}};
  assert.deepEqual(replica.apply(wire(producer.next(compacted))),compacted);
  assert.equal(producer.next(compacted),null);
  assert.throws(()=>replica.apply({sequence:99,base:98,docs:{}}),/resynchronization/);
});

test('notifications preceding attach response are buffered and sequence gaps reconnect with a new snapshot',async t=>{
  const views=[],errors=[]; let release,opens=0;
  const first=peer(view('initial')),second=peer(view('recovered',[entry(1)]));
  const attach=first.request.bind(first);
  first.request=async(...args)=>{ const result=await attach(...args); await new Promise(resolve=>{release=resolve;}); return result; };
  const stop=subscribe(first,views,{connect:async()=>++opens===1?first:second,retryMs:1,onError:error=>errors.push(error)});
  t.after(stop); await until(()=>release); first.notify(view('before reply')); release();
  await until(()=>views.length===2);
  assert.equal(views.at(-1).docs['pi.live'].generation.message.content[0].text,'before reply');
  first.emit('notification',{method:'session/view',params:{workspace_id:'work',session_id:'session',frame:{sequence:4,base:3,docs:{}}}});
  await until(()=>views.length===3); assert.equal(first.closed,true); assert.equal(errors.length,1);
  assert.equal(views.at(-1).entries[0].id,1);
  first.notify(view('stale')); assert.equal(views.length,3);
  stop(); assert.equal(second.closed,true);
});

test('session reconnect reattaches and disposal closes a delayed connection',async t=>{
  const views=[],errors=[]; let opens=0,finish;
  const first=peer(view('first')),second=peer(view('second'));
  const stop=subscribe(first,views,{connect:async()=>++opens===1?first:second,retryMs:1,onError:error=>errors.push(error)});
  t.after(stop); await until(()=>views.length===1); first.close(); await until(()=>views.length===2);
  assert.equal(errors.length,1); stop(); assert.equal(second.closed,true);
  const late=peer(view('late'));
  const dispose=subscribe(late,[],{connect:()=>new Promise(resolve=>{finish=resolve;})});
  dispose(); finish(late); await until(()=>late.closed); assert.deepEqual(late.requests,[]);
});
