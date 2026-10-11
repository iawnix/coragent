import assert from "node:assert/strict";
import test from "node:test";
import { existsSync } from "node:fs";
import { createPublicToolContracts } from '../../apps/agent/tools/contracts.mjs';
import Type, { Value } from '../../apps/agent/pi/typebox.mjs';
import { validateToolArguments } from '@earendil-works/pi-ai';

test("retired compute bootstrap and implementation have no compatibility modules", () => {
  for (const name of ["capability-host-bootstrap.mjs", "pi-native-compute.mjs"]) {
    assert.equal(existsSync(new URL(`../../apps/app-server/${name}`, import.meta.url)), false);
  }
});

test("canonical command adapters reject obsolete fields instead of dropping them", async () => {
  const { commandArguments, createCommandService } = await import("../../apps/agent/tools/commands.mjs");
  let called = false;
  const service = createCommandService({ execute() { called = true; } });
  for (const params of [{ jobId: "job_1" }, { intent_id: "calc_1" }, { job_id: "job_1", unknown: null }]) {
    assert.throws(() => service.execute("job.collect", "/unused", params), /schema_field_invalid/);
    assert.throws(() => commandArguments("job.collect", params), /schema_field_invalid/);
  }
  for (const params of [{ node_ref: "node_1" }, { storage_operation: "status" }]) {
    assert.throws(() => service.execute("research.read", "/unused", params), /schema_field_invalid/);
  }
  assert.equal(called, false);
  assert.deepEqual(commandArguments("job.collect", { job_id: "job_1" }), ["--job-id", "job_1"]);
});

test('task action contracts require their own payloads and reject ignored fields',()=>{
  const tools=createPublicToolContracts(Type);
  const check=(key,args)=>{
    validateToolArguments(tools[key],{type:'toolCall',id:'contract',name:tools[key].name,arguments:args});
    assert.equal(Value.Check(tools[key].parameters,args),true);
  };
  const base={expected_revision:1};
  const actions=[
    ['refine',{source_submission_ids:['12'],objective:'Updated objective'}],
    ['progress',{evidence_refs:['result_example']}],
    ['wait',{wait:{job_ids:['job_example'],mode:'all'}}],
    ['block',{reason:'Missing user input'}],
    ['propose_completion',{completion:[{criterion_id:'c1',evidence_refs:['a1']}]}],
    ['set_research',{research:{entry_node_ids:[],focus_node_ids:[]}}],
    ['apply_user_control',{control:'cancel',jobs:'cancel',source_submission_ids:['12']}],
  ];
  for (const [action,fields] of actions) {
    check('taskUpdate',{...base,action,...fields});
    assert.throws(()=>check('taskUpdate',{...base,action}));
  }
  assert.throws(()=>check('taskUpdate',{...base,action:'wait',wait:{job_ids:['job_example'],mode:'all'},completion:[{criterion_id:'c1',evidence_refs:['a1']}]}));
  assert.throws(()=>check('taskUpdate',{...base,action:'refine',source_submission_ids:['user_1']}));
  for (const control of ['pause','resume']) {
    const args={...base,action:'apply_user_control',control,source_submission_ids:['12']};
    check('taskUpdate',args);
    assert.throws(()=>check('taskUpdate',{...args,jobs:'keep'}));
  }
  const cancel={...base,action:'apply_user_control',control:'cancel',jobs:'keep',source_submission_ids:['12']};
  check('taskUpdate',cancel);
  for (const field of ['control','jobs','source_submission_ids']) {
    const args={...cancel}; delete args[field];
    assert.throws(()=>check('taskUpdate',args));
  }
  assert.throws(()=>check('taskUpdate',{...cancel,reason:'ignored'}));
  assert.throws(()=>check('taskUpdate',{...cancel,source_submission_ids:[]}));
  const begin={title:'Research',objective:'Compare candidates',criteria:[{id:'c1',description:'Evidence collected'}]};
  check('taskBegin',{...begin,source_submission_ids:['12']});
  assert.throws(()=>check('taskBegin',{...begin,source_submission_ids:['user_1']}));
});
