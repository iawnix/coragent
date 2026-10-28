import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';
import { subscribeSession } from '../../../apps/agent/terminal/connection.mjs';

const until=async predicate=>{for(let i=0;i<100;i++){if(predicate())return;await delay(5);}assert.fail('connection did not settle');};
function peer(read) {
  return Object.assign(new EventEmitter(),{closed:false,
    async request(method){return method==='session/query'?read():{};},
    close(){this.closed=true;this.emit('close',new Error('fixture disconnect'));},
    notify(){this.emit('notification',{method:'session/event',params:{workspace_id:'work',session_id:'session'}});},
  });
}

test('session subscription coalesces updates and continues refreshing after an in-flight read',async t=>{
  let finish,reads=0;const views=[];
  const connection=peer(()=>{reads++;return reads===2?new Promise(resolve=>{finish=resolve;}):{sequence:reads};});
  const stop=subscribeSession({connect:async()=>connection,workspaceId:'work',sessionId:'session',onView:view=>views.push(view),onError:assert.fail});
  t.after(stop);await until(()=>views.length===1);
  connection.notify();await until(()=>finish);
  for(let i=0;i<20;i++)connection.notify();await delay(25);
  finish({sequence:2});await until(()=>views.length===3);
  connection.notify();await until(()=>views.length===4);
  assert.deepEqual(views.map(view=>view.sequence),[1,2,3,4]);
  stop();assert.equal(connection.closed,true);
});

test('session reconnect reattaches and obtains a fresh snapshot; disposal closes a delayed connection',async t=>{
  const views=[],errors=[];let opens=0,finish;
  const first=peer(()=>({sequence:1})),second=peer(()=>({sequence:2}));
  const stop=subscribeSession({connect:async()=>++opens===1?first:second,workspaceId:'work',sessionId:'session',retryMs:1,
    onView:view=>views.push(view.sequence),onError:error=>errors.push(error)});
  t.after(stop);await until(()=>views.length===1);first.close();await until(()=>views.length===2);
  assert.deepEqual(views,[1,2]);assert.equal(errors.length,1);stop();assert.equal(second.closed,true);
  const late=peer(()=>assert.fail('disposed connection must not query'));
  const dispose=subscribeSession({connect:()=>new Promise(resolve=>{finish=resolve;}),workspaceId:'work',sessionId:'session',onView:assert.fail,onError:assert.fail});
  dispose();finish(late);await until(()=>late.closed);
});
