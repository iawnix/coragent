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
    ['correct_execution',{reason:'Original scheduler misread',execution_intent:{source_submission_id:'12',source_text:'Use TRI',scheduler:'tri'}}],
    ['progress',{evidence_refs:['result_example']}],
    ['wait',{wait:{job_ids:['job_example'],mode:'all'}}],
    ['block',{reason:'Missing user input',block_kind:'missing_user_input',resume_when:'The user supplies the missing input.'}],
    ['propose_completion',{completion_outcome:'full',completion:[{criterion_id:'c1',status:'met',assessment_ref:'art_1',evidence_refs:['art_2']}]}],
    ['set_research',{research:{entry_node_ids:[],focus_node_ids:[]}}],
    ['apply_user_control',{control:'cancel',jobs:'cancel',source_submission_ids:['12']}],
  ];
  for (const [action,fields] of actions) {
    check('taskUpdate',{...base,action,...fields});
    assert.throws(()=>check('taskUpdate',{...base,action}));
    for (const field of ['block_kind','resume_when','next_action']) {
      const value = field === 'block_kind' ? 'missing_user_input' : 'Concrete next step';
      const args = {...base,action,...fields,[field]:value};
      if (field === 'next_action' ? ['refine','progress'].includes(action) : action === 'block') check('taskUpdate',args);
      else assert.throws(()=>check('taskUpdate',args));
    }
  }
  for (const block_kind of ['resource_unavailable','execution_failure','budget_exhausted','scientific_dead_end']) {
    const args = {...base,action:'block',block_kind,reason:'Verified obstacle',resume_when:'The prerequisite becomes available.'};
    assert.throws(()=>check('taskUpdate',args));
    check('taskUpdate',{...args,evidence_refs:['result_1']});
  }
  const blocker = {...base,action:'block',reason:'Missing user input',block_kind:'missing_user_input',resume_when:'The user supplies the input.'};
  for (const field of ['reason','resume_when']) {
    assert.throws(()=>check('taskUpdate',{...blocker,[field]:' \n\t'}));
  }
  assert.throws(()=>check('taskUpdate',{...base,action:'progress',evidence_refs:['result_1'],next_action:' \n\t'}));
  assert.throws(()=>check('taskUpdate',{...base,action:'refine',source_submission_ids:['12'],next_action:' \n\t'}));
  for (const field of ['reason','block_kind','resume_when']) {
    const args = {...blocker}; delete args[field];
    assert.throws(()=>check('taskUpdate',args));
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
  const begin={title:'Research',objective:'Compare candidates',criteria:[{id:'c1',description:'Evidence collected'}],initial_plan:'Compare the candidates and record evidence.',next_action:'Read the candidate inputs and perform the first comparison.'};
  check('taskBegin',{...begin,source_submission_ids:['12']});
  for (const field of ['initial_plan','next_action']) {
    const args = {...begin,source_submission_ids:['12']}; delete args[field];
    assert.throws(()=>check('taskBegin',args));
    assert.throws(()=>check('taskBegin',{...begin,source_submission_ids:['12'],[field]:' \n\t'}));
  }
  assert.throws(()=>check('taskBegin',{...begin,source_submission_ids:['user_1']}));
});

test("partial closure contracts require the appropriate stopping evidence", () => {
  const schema = createPublicToolContracts(Type).taskUpdate.parameters;
  const base = { action: "propose_completion", expected_revision: 1, completion_outcome: "partial",
    completion: [{ criterion_id: "c1", status: "unmet", assessment_ref: "art_1", evidence_refs: ["result_1"] }] };
  for (const kind of ["user_requested", "budget_exhausted", "search_exhausted"]) {
    assert.equal(Value.Check(schema, { ...base, stop_basis: { kind, reason: "Stop reason" } }), false);
    const support = kind === "user_requested" ? { source_submission_ids: ["12"], source_text: "Stop and deliver partial findings" } : { evidence_refs: ["art_2"] };
    assert.equal(Value.Check(schema, { ...base, stop_basis: { kind, reason: "Stop reason", ...support } }), true);
  }
});
