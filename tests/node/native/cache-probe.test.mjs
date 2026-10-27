import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { runCacheProbe } from '../../../tools/test/cache-probe.mjs';
import { TEST_ROOT, pinnedPiSource } from './test-environment.mjs';

test('bounded synthetic probe exercises repeats, appends and a real adapter tool cycle without network', async t => {
  const outputDir=await mkdtemp(join(TEST_ROOT,'cache-probe-'));
  const previousFetch=globalThis.fetch;
  globalThis.fetch=()=>{throw Error('Network must not be used by the local probe');};
  t.after(async()=>{globalThis.fetch=previousFetch;await rm(outputDir,{recursive:true,force:true});});
  const emitted=[];
  const report=await runCacheProbe({mode:'local',sizeK:128,piRoot:pinnedPiSource(),outputDir},row=>emitted.push(row));
  assert.equal(report.completed,true);
  assert.equal(report.requests,4);
  assert.deepEqual(report.results.map(r=>r.stage),['cold','exact_repeat','append_user','tool_result']);
  assert.ok(report.results.every(r=>r.token_source==='fixture_counter'&&r.cache_mapping_matches));
  assert.equal(report.results[1].prefix.input_identical,true);
  assert.ok(report.results.slice(2).every(r=>r.prefix.tools_unchanged&&r.prefix.unchanged_leading_messages>50));
  assert.equal(report.results[2].stop_reason,'toolUse');
  assert.equal(report.results[3].stop_reason,'stop');
  assert.ok(report.results.slice(1).every(r=>r.prefix.cache_key_present===false));
  const log=await readFile(join(outputDir,'request-cache.jsonl'),'utf8');
  assert.equal(log.trim().split('\n').length,8);
  assert.doesNotMatch(log,/amber birch|probe_history|fixture-only|cache_probe_echo/);
  assert.deepEqual(JSON.parse(await readFile(join(outputDir,'report.json'),'utf8')),report);
  assert.equal(emitted.length,5);
});

test('unsupported scale or mode is rejected before provider setup', async () => {
  await assert.rejects(runCacheProbe({mode:'local',sizeK:800}),/invalid_probe_config/);
  await assert.rejects(runCacheProbe({mode:'automatic',sizeK:128}),/invalid_probe_config/);
});
