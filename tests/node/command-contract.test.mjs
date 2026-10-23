import assert from "node:assert/strict";
import test from "node:test";
import { existsSync } from "node:fs";
import { createPublicToolContracts } from '../../apps/agent/tools/contracts.mjs';
import Type, { Value } from '../../apps/agent/runtime/typebox.mjs';
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
    assert.throws(() => service.execute("job_collect", "/unused", params), /schema_field_invalid/);
    assert.throws(() => commandArguments("job_collect", params), /schema_field_invalid/);
  }
  for (const params of [{ node_ref: "node_1" }, { storage_operation: "status" }]) {
    assert.throws(() => service.execute("research_read", "/unused", params), /schema_field_invalid/);
  }
  for (const [command,params] of [
    ["research_create",{goal:"Compare routes",proposal:"Retired field"}],
    ["research_update",{node_id:"node_1",note:"Update",progress:"Retired field"}],
    ["research_update",{node_id:"node_1",note:"Update",proposal:"Retired field"}],
    ["research_result",{node_id:"node_1",conclusion:"Finding",progress:"Retired field"}],
  ]) assert.throws(()=>commandArguments(command,params),/schema_field_invalid/);
  for (const field of ["proposal","progress"]) {
    assert.throws(()=>commandArguments("research_read",{ref:"node_1",field}));
  }
  assert.equal(called, false);
  assert.deepEqual(commandArguments("job_collect", { job_id: "job_1" }), ["--job-id", "job_1"]);
});

test('task action contracts require their own payloads and reject ignored fields',()=>{
  const tools=createPublicToolContracts(Type);
  const check=(key,args)=>{
    validateToolArguments(tools[key],{type:'toolCall',id:'contract',name:tools[key].name,arguments:args});
    assert.equal(Value.Check(tools[key].parameters,args),true);
  };
  const base={expected_revision:1};
  check('task_update',{...base,action:'bind_execution'});
  check('task_update',{...base,action:'bind_execution',execution_target:{platform:'Com30',scheduler_entry:'qrun'}});
  for (const [field,value] of [['source_submission_ids',['12']],['objective','Ignored scope'],['reason','Ignored reason'],['execution_plan',{items:[]}]]) {
    assert.throws(()=>check('task_update',{...base,action:'bind_execution',[field]:value}));
  }
  const firstPlan={...base,action:'set_execution_plan',execution_target:{platform:'Com30',scheduler_entry:'qrun'},
    execution_plan:{items:[{id:'a',work_id:'a',resources:{cpus:1,memory_mb:512}}]}};
  check('task_update',firstPlan);
  assert.throws(()=>check('task_update',{...firstPlan,source_submission_ids:['12']}));
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
    check('task_update',{...base,action,...fields});
    assert.throws(()=>check('task_update',{...base,action}));
    for (const field of ['block_kind','resume_when','next_action']) {
      const value = field === 'block_kind' ? 'missing_user_input' : 'Concrete next step';
      const args = {...base,action,...fields,[field]:value};
      if (field === 'next_action' ? ['refine','progress'].includes(action) : action === 'block') check('task_update',args);
      else assert.throws(()=>check('task_update',args));
    }
  }
  for (const block_kind of ['resource_unavailable','execution_failure','budget_exhausted','scientific_dead_end']) {
    const args = {...base,action:'block',block_kind,reason:'Verified obstacle',resume_when:'The prerequisite becomes available.'};
    assert.throws(()=>check('task_update',args));
    check('task_update',{...args,evidence_refs:['result_1']});
  }
  const blocker = {...base,action:'block',reason:'Missing user input',block_kind:'missing_user_input',resume_when:'The user supplies the input.'};
  for (const field of ['reason','resume_when']) {
    assert.throws(()=>check('task_update',{...blocker,[field]:' \n\t'}));
  }
  assert.throws(()=>check('task_update',{...base,action:'progress',evidence_refs:['result_1'],next_action:' \n\t'}));
  assert.throws(()=>check('task_update',{...base,action:'refine',source_submission_ids:['12'],next_action:' \n\t'}));
  for (const field of ['reason','block_kind','resume_when']) {
    const args = {...blocker}; delete args[field];
    assert.throws(()=>check('task_update',args));
  }
  assert.throws(()=>check('task_update',{...base,action:'wait',wait:{job_ids:['job_example'],mode:'all'},completion:[{criterion_id:'c1',evidence_refs:['a1']}]}));
  assert.throws(()=>check('task_update',{...base,action:'refine',source_submission_ids:['user_1']}));
  for (const control of ['pause','resume']) {
    const args={...base,action:'apply_user_control',control,source_submission_ids:['12']};
    check('task_update',args);
    assert.throws(()=>check('task_update',{...args,jobs:'keep'}));
  }
  const cancel={...base,action:'apply_user_control',control:'cancel',jobs:'keep',source_submission_ids:['12']};
  check('task_update',cancel);
  for (const field of ['control','jobs','source_submission_ids']) {
    const args={...cancel}; delete args[field];
    assert.throws(()=>check('task_update',args));
  }
  assert.throws(()=>check('task_update',{...cancel,reason:'ignored'}));
  assert.throws(()=>check('task_update',{...cancel,source_submission_ids:[]}));
  const begin={title:'Research',objective:'Compare candidates',criteria:[{id:'c1',description:'Evidence collected'}],next_action:'Read the candidate inputs and perform the first comparison.'};
  check('task_begin',{...begin,source_submission_ids:['12']});
  assert.throws(()=>check('task_begin',{...begin,source_submission_ids:['12'],initial_plan:'Duplicate research plan'}));
  for (const field of ['next_action']) {
    const args = {...begin,source_submission_ids:['12']}; delete args[field];
    assert.throws(()=>check('task_begin',args));
    assert.throws(()=>check('task_begin',{...begin,source_submission_ids:['12'],[field]:' \n\t'}));
  }
  assert.throws(()=>check('task_begin',{...begin,source_submission_ids:['user_1']}));
});

test("partial closure contracts require the appropriate stopping evidence", () => {
  const schema = createPublicToolContracts(Type).task_update.parameters;
  const base = { action: "propose_completion", expected_revision: 1, completion_outcome: "partial",
    completion: [{ criterion_id: "c1", status: "unmet", assessment_ref: "art_1", evidence_refs: ["result_1"] }] };
  for (const kind of ["user_requested", "budget_exhausted", "search_exhausted"]) {
    assert.equal(Value.Check(schema, { ...base, stop_basis: { kind, reason: "Stop reason" } }), false);
    const support = kind === "user_requested" ? { source_submission_ids: ["12"], source_text: "Stop and deliver partial findings" } : { evidence_refs: ["art_2"] };
    assert.equal(Value.Check(schema, { ...base, stop_basis: { kind, reason: "Stop reason", ...support } }), true);
  }
});

test("canonical tool inventory excludes internal commands and rejects dotted aliases", async () => {
  const { PUBLIC_TOOL_NAMES } = await import("../../apps/agent/tools/contracts.mjs");
  const { COMMAND_IDS, createCommandService, parseSlashCommand } = await import("../../apps/agent/tools/commands.mjs");
  const contracts = createPublicToolContracts(Type);
  assert.deepEqual(Object.keys(contracts), [...PUBLIC_TOOL_NAMES]);
  for (const name of PUBLIC_TOOL_NAMES) {
    assert.equal(contracts[name].name, name);
    if (!name.startsWith("task_")) assert.ok(COMMAND_IDS.includes(name));
    for (const field of ["session_id", "principal", "read_basis", "execution_context"]) {
      assert.equal(Object.hasOwn(contracts[name].parameters.properties, field), false, `${name}.${field}`);
    }
  }
  for (const internal of ["research_source", "research_observe", "research_allocate_task", "job_prepare", "job_resolve_target", "job_manager_assess"]) {
    assert.ok(COMMAND_IDS.includes(internal));
    assert.equal(contracts[internal], undefined);
  }
  const calls = [];
  const service = createCommandService({ execute(invocation) { calls.push(invocation); } });
  for (const name of ["research.read", "job.start", "artifact.read", "constructor", "__proto__"]) {
    assert.throws(() => service.execute(name, "/unused"), /unsupported CoRAgent command/);
  }
  assert.equal(calls.length, 0);
  assert.deepEqual(parseSlashCommand("research", "read node_1"), { command: "research_read", params: { ref: "node_1" } });
  assert.deepEqual(parseSlashCommand("research", "search competing paths"), { command: "research_search", params: { query: "competing paths" } });
});

test("core tool adapters preserve command identity and inject trusted bindings", async () => {
  const { createCoreTools } = await import("../../apps/agent/tools/registry.mjs");
  const { validateCommandInvocation } = await import("../../apps/agent/tools/commands.mjs");
  const calls = [];
  const tools = createCoreTools({
    commandBridge: { async execute_command(command, params) {
      validateCommandInvocation(command, params);
      calls.push({ command, params });
      return {};
    } },
    getTaskBinding: async () => ({ user_task_id: "task_1", execution_context: {
      selection: { target: { platform: "selected", scheduler_entry: "main" }, route_digest: "sha256:" + "a".repeat(64) },
      policy: { max_in_flight: 1, max_attempts: 10 } } }),
  });
  const examples = {
    research_read: {}, research_search: { query: "evidence" }, research_create: { goal: "Investigate" },
    research_update: { node_id: "node_1", note: "Observed" }, research_result: { node_id: "node_1", conclusion: "Uncertain" },
    job_start: { node_id: "node_1", command: ["true"] }, job_status: { job_id: "job_1" },
    job_collect: { job_id: "job_1" }, job_cancel: { job_id: "job_1" }, job_probe: {}, job_platforms: {}, job_resources: {}, job_reconcile: { job_id: "job_1" },
    artifact_create: { name: "report.txt", content: "Evidence" }, artifact_register: { path: "input.txt" }, artifact_read: { artifact_id: "art_1" },
  };
  for (const tool of tools) {
    const args = examples[tool.name];
    assert.ok(args, tool.name);
    validateToolArguments(tool, { type: "toolCall", id: tool.name, name: tool.name, arguments: args });
    await tool.execute(args, { callId: tool.name, coragent: { workspace_root: "/unused", session_id: "trusted", operation_id: "operation", principal: "root_agent" } }, { abortSignal: new AbortController().signal });
    assert.equal(calls.at(-1).command, tool.name);
  }
  const start = calls.find(call => call.command === "job_start").params;
  assert.equal(start.session_id, "trusted");
  assert.deepEqual(start.execution_context.selection.target, { platform: "selected", scheduler_entry: "main" });
  assert.equal(start.execution_context.selection.route_digest, "sha256:" + "a".repeat(64));
  assert.equal(start.user_task_id, "task_1");
});
