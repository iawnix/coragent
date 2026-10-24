import assert from "node:assert/strict";
import test from "node:test";
import { createRefreshLoop, createTerminalCommands } from "../../../apps/agent/terminal/commands/facet.mjs";
import { createClientQueries } from "../../../apps/agent/runtime/services/queries.mjs";
import { createTerminalSession, runTerminalSessions } from "../../../apps/agent/terminal/session.mjs";
import { parseSlashCommand, slashCompletions, SLASH_COMMAND_NAMES } from "../../../apps/agent/tools/commands.mjs";

const row = (id, workspace = "remote") => ({ session_id: id, workspace_id: workspace });
const emptyResearchBrief = () => ({ schema_version: 'research-brief/1',
  scope: { entry_node_ids: [], focus_node_ids: [] }, findings: [], contradictions: [], uncertainties: [],
  limitations: [], follow_up: [], source_refs: [], coverage: { omitted: {} }, projection_status: 'complete' });
const researchRecord = (ref, value) => {
  const text = JSON.stringify(value);
  return { schema_version: 'research-read/2', ref, content_sha256: 'sha256:fixture-record', text,
    offset: 0, offset_unit: 'unicode_characters', total_characters: [...text].length, next_offset: null };
};

test('status sources refresh independently, coalesce bursts, and ignore responses after disposal', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const applied = [], telemetryReads = [];
  let monitorReads = 0;
  const telemetry = createRefreshLoop({
    read: () => new Promise(resolve => telemetryReads.push(resolve)),
    apply: value => applied.push(['telemetry',value]), onError: assert.fail,
  });
  const monitor = createRefreshLoop({read:async()=>++monitorReads,
    apply:value=>applied.push(['monitor',value]),onError:assert.fail});
  const flush = () => new Promise(resolve => setImmediate(resolve));
  try {
    const pending = telemetry.refresh();
    await monitor.refresh();
    assert.deepEqual(applied,[['monitor',1]]);
    for (let index=0;index<100;index++) telemetry.schedule();
    t.mock.timers.tick(5000); await flush();
    assert.deepEqual(applied,[['monitor',1],['monitor',2]]);
    assert.equal(telemetryReads.length,1);
    telemetryReads[0]('first'); await pending;
    assert.deepEqual(applied.at(-1),['telemetry','first']);
    t.mock.timers.tick(249); await flush();
    assert.equal(telemetryReads.length,1);
    t.mock.timers.tick(1); await flush();
    assert.equal(telemetryReads.length,2);
    telemetry.stop(); monitor.stop();
    const before = [...applied];
    telemetryReads[1]('disposed'); await flush();
    t.mock.timers.tick(20000); await flush();
    await telemetry.refresh(); monitor.schedule();
    assert.deepEqual(applied,before);
    assert.equal(telemetryReads.length,2);
    assert.equal(monitorReads,2);
  } finally { telemetry.stop(); monitor.stop(); }
});

test('refresh failures remain local and scheduled updates do not starve under repeated notifications', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  let reads=0;
  const applied=[],errors=[];
  const refresh=createRefreshLoop({read:async()=>{
    if (++reads===1) throw new Error('connection unavailable');
    return reads;
  },apply:value=>applied.push(value),onError:error=>errors.push(error.message)});
  try {
    await refresh.refresh();
    assert.deepEqual(errors,['connection unavailable']);
    for(let index=0;index<5;index++) { refresh.schedule(); t.mock.timers.tick(50); }
    await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(applied,[2]);
    assert.equal(reads,2);
  } finally { refresh.stop(); }
});

test('slash completion follows argument positions and preserves case-sensitive IDs', () => {
  const values = prefix => (slashCompletions('monitor', prefix) || []).map(item => item.value);
  assert.deepEqual(values('ta'), ['tasks ', 'task ']);
  assert.deepEqual(values('task '), ['task pause ', 'task resume ', 'task cancel ']);
  assert.deepEqual(values('task pause '), []);
  assert.deepEqual(values('task cancel TaskABC '), ['task cancel TaskABC --keep-jobs ', 'task cancel TaskABC --cancel-jobs ']);
  assert.deepEqual(values('jobs --task '), []);
  assert.deepEqual(values('jobs --task TaskABC '), ['jobs --task TaskABC --limit ', 'jobs --task TaskABC --cursor ']);
  assert.deepEqual(values('run RunABC --limit 5 '), ['run RunABC --limit 5 --cursor ']);
  assert.deepEqual(values('health '), []);
  assert.deepEqual(values('jobs\n'), []);
  assert.equal(slashCompletions('research', 'search some text'), null);
  assert.ok(slashCompletions('monitor', 'jobs')[0].description);
});

test('command validation explains incomplete input without invoking any operation', () => {
  const commands = createTerminalCommands({});
  const monitor = commands.find(command => command.name === 'monitor');
  assert.equal(monitor.validate(''), undefined);
  assert.match(monitor.validate('task pause'), /Missing task ID/);
  assert.match(monitor.validate('task cancel TaskABC'), /Choose --keep-jobs or --cancel-jobs/);
  assert.match(monitor.validate('jobs --limit'), /Missing value for --limit/);
  assert.match(monitor.validate('jobs --limit 200'), /integer from 1 to 100/);
  assert.equal(monitor.validate('task pause TaskABC'), undefined);
});

test('research grammar separates the current overview, saved questions and text search', () => {
  for (const [input, command, params] of [
    ['', 'research_read', { view: 'brief' }],
    ['read', 'research_search', { kind: 'node', query: '' }],
    ['read --offset 20', 'research_search', { kind: 'node', query: '', offset: 20 }],
    ['read --limit 5 --offset 20', 'research_search', { kind: 'node', query: '', limit: 5, offset: 20 }],
    ['read node_7', 'research_read', { ref: 'node_7' }],
    ['search', 'research_search', { query: '' }],
    ['search --offset 20', 'research_search', { query: '', offset: 20 }],
    ['search competing paths', 'research_search', { query: 'competing paths' }],
    ['search competing paths --offset 20 --limit 5', 'research_search', { query: 'competing paths', offset: 20, limit: 5 }],
  ]) assert.deepEqual(parseSlashCommand('research', input), { command, params });
  for (const input of ['detail node_7', 'read node_7 extra', 'read --offset', 'read --offset -1',
    'read --offset 1.5', 'read --offset 1 --offset 2', 'read --limit 0', 'read --limit 101',
    'search term --offset', 'search term --unknown value']) {
    assert.throws(() => parseSlashCommand('research', input), /Usage/);
  }
});

test("worker queries bind identity and admit only read-only research arguments", async () => {
  const calls = [];
  const prompt = { effective: "worker prompt", contributors: [] };
  const record = researchRecord('note_123', { ref: 'note_123', content: 'Saved research record' });
  const queries = createClientQueries({ workspaceId: "remote", sessionId: "one", promptManifest: prompt,
    queryBridge: { async execute_command(...args) { calls.push(args); return record; } },
  });
  assert.deepEqual(await queries.research("read note_123"), {
    workspace_id: "remote", session_id: "one", result: record,
  });
  assert.deepEqual(calls, [["research_read", { ref: "note_123", offset: 0, limit: 32000 }]]);
  for (const input of ["change x", "storage bootstrap", "summary --root /local", { root: "/local" }]) {
    assert.ok((await queries.research(input)).error);
  }
  assert.equal(calls.length, 1);
  assert.equal((await queries.systemPrompt()).result, prompt);
});

test("command registry, parsing, native selection, and worker reads agree", async () => {
  const shown = [];
  let quit = 0;
  const resumed = [];
  const queries = createClientQueries({ workspaceId: "remote", sessionId: "one",
    promptManifest: { effective: "actual worker prompt", contributors: [{ origin: "native", source: "/remote/prompt" }], sha256: "digest" },
    currentTask: async () => ({ user_task_id: 'task_1', title: 'Remote research', objective: 'remote research result', state: 'active',
      research: { entry_node_ids: [], focus_node_ids: [] } }),
    queryBridge: { async execute_command() { return emptyResearchBrief(); } },
  });
  let choice;
  const ui = { showStatus(text) { shown.push(text); }, async select(title) { shown.push(title); return choice; } };
  const commands = createTerminalCommands({ ui, queries, show: async (title, body) => shown.push(`${title}\n${body}`), session: {
    sessionId: "one", quit() { quit++; }, async list() { return [row("one"), row("two")]; }, async resume(id) { resumed.push(id); },
  } });
  assert.deepEqual(commands.map((c) => `/${c.name}`), SLASH_COMMAND_NAMES);
  assert.throws(() => parseSlashCommand("debug", "prompt"), /unsupported/);
  assert.throws(() => parseSlashCommand("sys-prompt", "unexpected"), /Usage/);
  const run = (name, args = "") => commands.find((c) => c.name === name).run(args, {});
  await run("research");
  await run("sys-prompt");
  assert.match(shown.join("\n"), /remote research result/);
  assert.match(shown.join("\n"), /actual worker prompt/);
  assert.match(shown.join("\n"), /\/remote\/prompt/);
  await run("resume"); // Escape/cancel
  assert.deepEqual(resumed, []);
  choice = "two";
  await run("resume");
  assert.deepEqual(resumed, ["two"]);
  await run("quit", "bad");
  assert.equal(quit, 0);
  await run("quit");
  assert.equal(quit, 1);
});

test("resume rejects unavailable or foreign sessions and checks Host response identity", async () => {
  const calls = [];
  const switched = [];
  let wrong = false;
  const session = createTerminalSession({ workspaceId: "remote", sessionId: "one", switchSession: (id) => switched.push(id),
    async request(method, params) {
      calls.push([method, params]);
      if (method === "session/list") return { sessions: [row("one"), row("two"), row("foreign", "elsewhere")] };
      return { session: row("two", wrong ? "elsewhere" : "remote"), client: { session_id: "two" } };
    },
  });
  await session.resume("one");
  assert.equal(calls.length, 0);
  for (const id of ["missing", "foreign"]) await assert.rejects(session.resume(id), /not available/);
  assert.equal(calls.some(([method]) => method === "session/resume"), false);
  wrong = true;
  await assert.rejects(session.resume("two"), /unexpected/);
  assert.deepEqual(switched, []);
  wrong = false;
  await session.resume("two");
  assert.deepEqual(switched, ["two"]);
  assert.equal(calls.at(-1)[1].workspace_id, "remote");
});

test("session loop waits for disposal before switching and quit does not call the Host", async () => {
  const events = [];
  let session;
  await runTerminalSessions({ command: { sessionId: "one" }, workspaceId: "remote",
    async request(method) {
      if (method === "session/list") return { sessions: [row("one"), row("two")] };
      assert.equal(method, "session/resume");
      return { session: row("two"), client: { session_id: "two" } };
    },
    createFacet(value) { session = value; return {}; },
    async run(command, { signal }) {
      events.push(`open ${command.sessionId}`);
      if (command.sessionId === "one") await session.resume("two");
      else session.quit();
      assert.equal(signal.aborted, true);
      await new Promise((resolve) => setImmediate(resolve));
      events.push(`disposed ${command.sessionId}`);
    },
  });
  assert.deepEqual(events, ["open one", "disposed one", "open two", "disposed two"]);
});

test("document commands pass complete text to the document surface", async () => {
  const shown = [];
  const commands = createTerminalCommands({
    ui: { showStatus() {} },
    show: async (title,body) => shown.push({title,body}),
    queries: { async systemPrompt() { return { workspace_id: "remote", session_id: "one", result: { effective: Array.from({length:40},(_,i)=>`line ${i}`).join("\n") } }; } },
    session: { sessionId: "one" },
  });
  await commands.find(c=>c.name === "sys-prompt").run("",{});
  assert.equal(shown[0].title,"System prompt");
  assert.match(shown[0].body,/line 0\n/);
  assert.match(shown[0].body,/line 39/);
});

test('research query errors expose bounded diagnostic facts for F2 details', async () => {
  const shown=[];
  const commands=createTerminalCommands({session:{sessionId:'one',workspaceId:'remote'},
    ui:{showStatus:(...args)=>shown.push(args)},
    queries:{async research(){return {session_id:'one',workspace_id:'remote',error:{
      message:'Python runtime request timed out: execute_command',code:'kernel_request_timeout',
      details:{command:'research_read',request_id:'q17',elapsed_ms:30000,params:{secret:'PRIVATE'},raw_output:'PRIVATE'},
    }};}},
  });
  await commands.find(command=>command.name==='research').run('',{});
  assert.equal(shown[0][0], 'Python runtime request timed out: execute_command\nCode: kernel_request_timeout\n'
    + 'Command: research_read\nRequest: q17\nElapsed: 30000 ms');
  assert.equal(shown[0][2],'error');
  assert.doesNotMatch(shown[0][0],/PRIVATE|params|raw_output/);
});

test('saved research navigation pages by title and opens the selected canonical record', async () => {
  const calls = [], choices = [], shown = [];
  const detail = researchRecord('node_2', {
    node: { id: 'node_2', title: 'Second research question', goal: 'Check evidence', status: 'open', plan: 'Compare candidates' },
    assessment: null, review_notices: [], results: [], recent_notes: { records: [] }, related_nodes: [],
  });
  const commands = createTerminalCommands({ session: { sessionId: 'one', workspaceId: 'remote' },
    ui: { showStatus: assert.fail, async select(_title, options) {
      choices.push(options);
      return choices.length === 1 ? options.find(option => /next|more/i.test(option.label))?.value : 'node_2';
    } },
    queries: { async research(input) {
      const invocation = parseSlashCommand('research', input);
      calls.push(invocation);
      const result = invocation.command === 'research_read' ? detail : {
        schema_version: 'research-search/2', total: 2, next_offset: invocation.params.offset ? null : 1,
        records: [{ ref: invocation.params.offset ? 'node_2' : 'node_1', kind: 'node',
          title: invocation.params.offset ? 'Second research question' : 'First research question' }],
      };
      return { session_id: 'one', workspace_id: 'remote', result };
    } },
    show: async (title, body) => shown.push({ title, body }),
  });
  await commands.find(command => command.name === 'research').run('read', {});
  assert.equal(choices.length, 2);
  assert.equal(choices[0].find(option => option.value === 'node_1').label, 'First research question');
  assert.equal(choices[1].find(option => option.value === 'node_2').label, 'Second research question');
  assert.equal(calls[0].command, 'research_search');
  assert.equal(calls[1].params.offset, 1);
  assert.deepEqual(calls[2], { command: 'research_read', params: { ref: 'node_2' } });
  assert.equal(shown.length, 1);
  assert.match(shown[0].body, /Second research question/);
  assert.match(shown[0].body, /Check evidence/);
  assert.doesNotMatch(shown[0].body, /"schema_version"|"node"\s*:/);
});

test('closing the saved research selector never changes focus or starts a detail read', async () => {
  const calls = [];
  const commands = createTerminalCommands({ session: { sessionId: 'one', workspaceId: 'remote' },
    ui: { showStatus: assert.fail, async select() { return undefined; } }, show: assert.fail,
    queries: { async research(input) {
      calls.push(input);
      return { session_id: 'one', workspace_id: 'remote', result: {
        schema_version: 'research-search/2', total: 1, next_offset: null,
        records: [{ ref: 'node_1', kind: 'node', title: 'Saved question' }],
      } };
    } },
  });
  await commands.find(command => command.name === 'research').run('read', {});
  assert.deepEqual(calls, ['read']);
});

test('research navigation checks worker identity before displaying each page', async () => {
  const errors = [];
  let reads = 0, selections = 0;
  const commands = createTerminalCommands({ session: { sessionId: 'one', workspaceId: 'remote' },
    ui: { showStatus(message) { errors.push(message); }, async select(_title, options) {
      selections++;
      return options.find(option => /next|more/i.test(option.label))?.value;
    } }, show: assert.fail,
    queries: { async research() {
      reads++;
      return { session_id: reads === 1 ? 'one' : 'different', workspace_id: 'remote', result: {
        schema_version: 'research-search/2', total: 2, next_offset: reads === 1 ? 1 : null,
        records: [{ ref: 'node_1', kind: 'node', title: 'Saved question' }],
      } };
    } },
  });
  await commands.find(command => command.name === 'research').run('read', {});
  assert.equal(reads, 2);
  assert.equal(selections, 1);
  assert.match(errors[0], /different session/);
});

test('health details keep empty values and nested fields on their own rows', async () => {
  const result = {nodes:[{id:'node_1',input_refs:[],progress:{},assessment_ref:null,
    content_omitted:false,revision:0,plan:'First line\nSecond line',subjects:['中文','second']}],tasks:[]};
  const {formatMonitor} = await import('../../../apps/agent/terminal/commands/monitor.mjs');
  const body = formatMonitor('monitor/health',result);
  assert.equal(body, 'nodes:\n  • id: node_1\n    input refs: []\n    progress: {}\n    assessment ref: —\n'
    + '    content omitted: false\n    revision: 0\n    plan: First line\n      Second line\n'
    + '    subjects:\n      • 中文\n      • second\ntasks: []');
  assert.match(formatMonitor('monitor/jobs',{items:[]}),/^No entries/);
});

test("usage and monitor use separate live panels while documents choose reading surfaces", async () => {
  const shown=[];
  let usage='Total tokens: 10', monitor='Running: 1';
  const commands=createTerminalCommands({
    ui:{showStatus(message){throw new Error(message);}}, session:{sessionId:'one',async monitor(){return {}; }},
    show:async (title,body,context,command,scope,mode)=>shown.push({title,body,command,scope,mode}),
    usage:()=>usage,monitor:()=>monitor,
    queries:{async systemPrompt(){return {session_id:'one',result:{effective:'prompt'}};},
      async research(){return {session_id:'one',result:emptyResearchBrief(),task:null};}},
  });
  for(const name of ['usage','monitor','sys-prompt','research']) await commands.find(c=>c.name===name).run('',{});
  assert.deepEqual(shown.map(item=>item.mode),['panel','panel','page','auto']);
  assert.equal(shown[0].body(),'Total tokens: 10');assert.equal(shown[1].body(),'Running: 1');
  usage='Total tokens: 20';monitor='Running: 2';
  assert.equal(shown[0].body(),'Total tokens: 20');assert.equal(shown[1].body(),'Running: 2');
  assert.throws(()=>parseSlashCommand('monitor','unexpected'),/Usage/);
});

test('Monitor grammar separates user tasks, compute jobs and execution records', () => {
  for (const [input, method, fields] of [
    ['', 'monitor/overview', {}], ['tasks --limit 5 --cursor next', 'monitor/tasks', {limit:5,cursor:'next'}],
    ['task t1', 'monitor/task/read', {user_task_id:'t1'}],
    ['task pause t1', 'monitor/task/pause', {user_task_id:'t1'}],
    ['task resume t1', 'monitor/task/resume', {user_task_id:'t1'}],
    ['task cancel t1 --keep-jobs', 'monitor/task/cancel', {user_task_id:'t1',jobs:'keep'}],
    ['task cancel t1 --cancel-jobs', 'monitor/task/cancel', {user_task_id:'t1',jobs:'cancel'}],
    ['jobs --task t1', 'monitor/jobs', {user_task_id:'t1'}],
    ['job j1', 'monitor/job/read', {job_id:'j1'}],
    ['job cancel j1', 'monitor/job/cancel', {job_id:'j1'}],
    ['runs --task t1', 'monitor/runs', {user_task_id:'t1'}],
    ['run r1', 'monitor/run/read', {run_id:'r1'}], ['health', 'monitor/health', {}],
  ]) assert.deepEqual(parseSlashCommand('monitor', input), {command:'client.monitor',params:{method,...fields}});
  for (const input of ['status', 'enable', 'disable', 'task', 'task cancel t1', 'task cancel t1 --keep-jobs --cancel-jobs',
    'task pause', 'job cancel', 'health extra', 'jobs --task', 'jobs --limit 0', 'jobs --limit 101',
    'jobs --task t1 --task t2', 'jobs --root /tmp', 'jobs --cursor 50', 'tasks --task t1']) assert.throws(() => parseSlashCommand('monitor', input), /Usage/);
});

test('Monitor task controls use current revision and direct Host requests without model input', async () => {
  const calls=[];
  const session=createTerminalSession({workspaceId:'w',sessionId:'s',async request(method,params){
    calls.push([method,params]);
    return {items:[{user_task_id:'t1',revision:7}],next_cursor:null};
  }});
  await session.monitor('monitor/tasks',{limit:5});
  assert.deepEqual(calls,[['monitor/tasks',{workspace_id:'w',session_id:'s',limit:5}]]);
  await session.monitor('monitor/task/pause',{user_task_id:'t1'});
  assert.equal(calls[1][0],'monitor/tasks');
  assert.deepEqual(calls[1][1],{workspace_id:'w',session_id:'s',limit:100});
  assert.equal(calls[2][0],'monitor/task/pause');
  assert.equal(calls[2][1].expected_revision,7);
  assert.match(calls[2][1].request_id,/^terminal-monitor-/);
  assert.equal(calls.some(([method])=>method==='input/send'),false);
});

test("closing a presentation prevents a delayed Host response from reopening it", async () => {
  let session;
  let reply;
  let started;
  const requested = new Promise((resolve) => { started = resolve; });
  let resume;
  await runTerminalSessions({ command: { sessionId: "one" }, workspaceId: "remote",
    async request(method) {
      if (method === "session/list") return { sessions: [row("two")] };
      started();
      return new Promise((resolve) => { reply = resolve; });
    },
    createFacet(value) { session = value; return {}; },
    async run() { resume = session.resume("two"); await requested; },
  });
  assert.equal(session.signal.aborted, true);
  const rejected = assert.rejects(resume, { name: "AbortError" });
  reply({ session: row("two"), client: { session_id: "two" } });
  await rejected;
});

test('Monitor run detail pagination is explicit and bounded', () => {
  assert.deepEqual(parseSlashCommand('monitor', 'run r1 --cursor c2 --limit 10').params,
    {method:'monitor/run/read',run_id:'r1',cursor:'c2',limit:10});
  assert.throws(() => parseSlashCommand('monitor', 'run r1 --limit 0'), /Usage/);
  assert.throws(() => parseSlashCommand('monitor', 'run r1 --cursor c1 --cursor c2'), /Usage/);
});

test('Monitor views keep tool payloads out of user task and Job details', async () => {
  const {formatMonitor} = await import('../../../apps/agent/terminal/commands/monitor.mjs');
  const detail = formatMonitor('monitor/job/read', {job:{job_id:'j1',state:'succeeded',collection_state:'not_collected',
    command:['SECRET_COMMAND'],metadata:{key:'SECRET_METADATA'}}});
  assert.match(detail,/Execution: succeeded/);
  assert.match(detail,/Collection: not_collected/);
  assert.doesNotMatch(detail,/Analysis: Not recorded/);
  assert.doesNotMatch(detail,/SECRET_/);
  assert.match(formatMonitor('monitor/runs',{items:[],next_cursor:'c2'},{user_task_id:'t1',limit:5}),
    /Next page: \/monitor runs --task t1 --limit 5 --cursor c2/);
  assert.match(formatMonitor('monitor/run/read',{run:{run_id:'r1'},items:[],next_cursor:'c3'},{run_id:'r1'}),
    /Next page: \/monitor run r1 --cursor c3/);
});

test('Monitor overview stays compact and links to detailed views', async () => {
  const {formatMonitor} = await import('../../../apps/agent/terminal/commands/monitor.mjs');
  const overview = formatMonitor('monitor/overview', {
    task: {user_task_id: 't1', title: 'Research', objective: 'Compare paths', state: 'waiting',
      wait: {job_count: 1, mode: 'all'}, reason: null, progress: null,
      next_action: 'Inspect the computed result'},
    jobs: {scope: 'task', active: [{job_id: 'job_1', state: 'running'}],
      counts: {running: 1, queued: 0, total: 1}},
    continuation: {state: 'waiting'},
  });
  assert.match(overview, /Task: Research/);
  assert.match(overview, /Task jobs: 1 running · 0 queued · 1 total/);
  assert.match(overview, /Next: Inspect the computed result/);
  assert.match(overview, /Task status: Waiting for compute/);
  assert.match(overview, /Details: Waiting for compute. Continues when ready./);
  assert.doesNotMatch(overview, /Research review|Automatic continuation: On/);
  assert.match(overview, /\/monitor task t1 · \/monitor jobs --task t1/);
  assert.doesNotMatch(overview, /Delivery criteria|Compute jobs|Analysis: Not recorded/);
});

test('execution records label model and tool operations and expose safe failure facts', async () => {
  const {formatMonitor} = await import('../../../apps/agent/terminal/commands/monitor.mjs');
  const result = formatMonitor('monitor/run/read', {run:{run_id:'r1',user_task_id:'t1'},items:[
    {pi_task_id:'g1',kind:'pi.generation',state:'terminal',outcome:'succeeded',error:null},
    {pi_task_id:'tool1',kind:'pi.tool',state:'terminal',outcome:'succeeded',tool_name:'job_start',result_entry_id:'entry1',
      error:{code:'invalid_request',failure_class:'validation',retryable:false,action_outcome:'not_started'},raw_output:'SECRET_OUTPUT'},
  ],next_cursor:null},{run_id:'r1'});
  assert.match(result,/Model request · terminal \/ succeeded/);
  assert.match(result,/Tool call: job_start/);
  assert.match(result,/Error: invalid_request/);
  assert.match(result,/Retryable: No/);
  assert.match(result,/Result entry: entry1/);
  assert.doesNotMatch(result,/SECRET_OUTPUT/);
});
