import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile, readFile, readdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { DatabaseSync } from 'node:sqlite';
import test from 'node:test';
import { TEST_ROOT, TEST_SOCKET_ROOT, pinnedPiSource, managedPython } from './test-environment.mjs';
import { createSessionCatalog } from '../../../apps/agent/runtime/session-catalog.mjs';
import { startSessionWorker } from '../../../apps/agent/runtime/worker-process.mjs';
import { createCoRAgentHarnessBackend } from '../../../apps/agent/runtime/backend.mjs';
import { startCoRAgentHost } from '../../../apps/agent/host/server.mjs';
import { connectHost } from '../../../apps/agent/transport/host-client.mjs';
import { backupBeforeMigration } from '../../../apps/agent/runtime/storage.mjs';

async function fixture(t) {
  const root=await mkdtemp(join(TEST_ROOT,'lifecycle-'));
  const socket=await mkdtemp(join(TEST_SOCKET_ROOT,'l-'));
  const workspaceRoot=join(root,'workspaces'),cwd=join(workspaceRoot,'work');
  const saved={PI_AGENT_DIR:process.env.PI_AGENT_DIR,PI_CODING_AGENT_DIR:process.env.PI_CODING_AGENT_DIR};
  const agent=join(root,'agent');await mkdir(agent);
  process.env.PI_AGENT_DIR=agent;process.env.PI_CODING_AGENT_DIR=agent;
  await writeFile(join(agent,'models.json'),JSON.stringify({providers:{fixture:{api:'openai-completions',apiKey:'fixture-only',baseUrl:'http://127.0.0.1:9/v1',
    models:[{id:'fixture',name:'Fixture',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:128000,maxTokens:4096}]}}}));
  await promisify(execFile)(managedPython(),['apps/cli/workspace_mode.py','--root',cwd,'--workspace-id','work']);
  t.after(async()=>{for(const [key,value] of Object.entries(saved))if(value===undefined)delete process.env[key];else process.env[key]=value;
    await rm(root,{recursive:true,force:true});await rm(socket,{recursive:true,force:true});});
  const options={sourceRoot:pinnedPiSource(),packageRoot:resolve('.'),workspaceRoot,serverDirectory:socket,sessionDir:join(root,'sessions'),stateRoot:join(root,'state'),model:{provider:'fixture',id:'fixture'}};
  return {root,socket,cwd,options};
}

test('Host services are available without Pi server/client/plugin packages or an active session',{timeout:30000},async t=>{
  const {options,socket}=await fixture(t);
  const backend=await createCoRAgentHarnessBackend(options);
  const host=await startCoRAgentHost({socketPath:join(socket,'host.sock'),workspaceRoot:options.workspaceRoot,stateRoot:options.stateRoot,sessionBackend:backend,monitorPollMs:0});
  try {
    const peer=await connectHost({socketPath:host.socketPath});
    try {
      assert.deepEqual((await peer.request('session/list',{workspace_id:'work'})).sessions,[]);
      const created=await peer.request('session/create',{workspace_id:'work',request_id:'create',session_id:'one',presentation:'terminal'});
      assert.equal(created.client.socket_path,host.socketPath);
      const reads=await Promise.all(Array.from({length:8},()=>peer.request('session/read',{workspace_id:'work',session_id:'one'})));
      assert.ok(reads.every(result=>result.session.online));
      await assert.rejects(peer.request('session/query',{workspace_id:'work',session_id:'one',query:'arbitrary-service'}),{code:'invalid_query'});
      await assert.rejects(peer.request('session/compact',{workspace_id:'work',session_id:'one',request_id:'bad-compact',instructions:{}}),{code:'invalid_input'});
      await peer.request('session/remove',{workspace_id:'work',session_id:'one',request_id:'remove'});
      assert.deepEqual((await peer.request('session/list',{workspace_id:'work'})).sessions,[]);
    } finally {peer.close();}
  } finally {await host.close();}
  assert.equal((await readdir(socket)).some(file=>file.endsWith('.sock')),false);
});

test('SQLite upgrade takes a WAL-consistent v1 backup and never overwrites it',{timeout:30000},async t=>{
  const {options,cwd}=await fixture(t);
  const catalog=createSessionCatalog(options.sessionDir);
  const metadata=await catalog.create({workspaceId:'work',sessionId:'legacy',cwd});
  const database=join(metadata.path,'session.sqlite');
  const {createSqliteMigrations}=await import(pathToFileURL(join(pinnedPiSource(),'packages/durable/src/storage/sqlite/migrations.ts')));
  const {DEFAULT_SQLITE_SCHEMA}=await import(pathToFileURL(join(pinnedPiSource(),'packages/durable/src/storage/sqlite/schema.ts')));
  const db=new DatabaseSync(database);
  let worker;
  try {
    db.exec('PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0; CREATE TABLE durable_schema (singleton INTEGER PRIMARY KEY,version INTEGER); INSERT INTO durable_schema VALUES (1,1)');
    for(const sql of createSqliteMigrations(DEFAULT_SQLITE_SCHEMA)[0].statements)db.exec(sql);
    db.exec("CREATE TABLE legacy_evidence(value TEXT); INSERT INTO legacy_evidence VALUES ('synthetic legacy evidence')");
    await backupBeforeMigration(database);
    const backup=new DatabaseSync(database+'.pre-pi-1.4',{readOnly:true});
    try {assert.equal(backup.prepare('SELECT version FROM durable_schema').get().version,1);
      assert.equal(backup.prepare('SELECT value FROM legacy_evidence').get().value,'synthetic legacy evidence');}
    finally {backup.close();}
    const original=await readFile(database+'.pre-pi-1.4');
    worker=startSessionWorker({...options,metadata,producerToken:'fixture-only',onView(){}});
    await worker.startup;
    assert.equal(db.prepare('SELECT version FROM durable_schema').get().version,2);
    assert.equal(db.prepare('SELECT value FROM legacy_evidence').get().value,'synthetic legacy evidence');
    await worker.close();worker=undefined;
    await backupBeforeMigration(database);
    assert.deepEqual(await readFile(database+'.pre-pi-1.4'),original);
  } finally {await worker?.close();db.close();}
});

test('a killed Worker releases its single-writer lease for a recovered process',{timeout:65000},async t=>{
  const {options,cwd}=await fixture(t);
  const metadata=await createSessionCatalog(options.sessionDir).create({workspaceId:'work',sessionId:'crash',cwd});
  let first,second;
  try {
    first=startSessionWorker({...options,metadata,producerToken:'fixture-only',onView(){}});
    await first.startup;
    const waiting=startSessionWorker({...options,metadata,producerToken:'fixture-only',onView(){}});second=waiting;
    let ready=false;const started=waiting.startup.then(view=>{ready=true;return view;});
    await new Promise(resolve=>setTimeout(resolve,200));assert.equal(ready,false,'only one writer can open the database');
    process.kill(first.pid,'SIGKILL');await first.close();first=undefined;
    const view=await started;assert.ok(view.docs['pi.agent']);
    await second.close();second=undefined;
  } finally {await second?.close();await first?.close();}
});
