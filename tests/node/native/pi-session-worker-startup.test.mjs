import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import { createServer } from "node:http";
import { TEST_ROOT, TEST_SOCKET_ROOT, retainPiDiagnostics, managedPython, pinnedPiSource, assertInstalledRuntime } from "./test-environment.mjs";

const execute = promisify(execFile);
const sourceRoot = pinnedPiSource();
const packageRoot = resolve(process.env.CORAGENT_TEST_PACKAGE_ROOT || process.cwd());

test("SSH input reassembles standard F2 fragments throughout the Escape timeout", async t => {
  const [{ StdinBuffer }, { resolveEscapeTimeoutMs }] = await Promise.all([
    import(pathToFileURL(join(sourceRoot, "packages/tui/src/stdin-buffer.ts"))),
    import(pathToFileURL(join(sourceRoot, "packages/tui/src/terminal.ts"))),
  ]);
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const escapeTimeout = resolveEscapeTimeoutMs({ SSH_TTY: "/dev/pts/fixture" });
  assert.equal(escapeTimeout, 100);
  for (const sequence of ["\x1bOQ", "\x1b[12~"]) {
    const buffer = new StdinBuffer({ escapeTimeout });
    const received = [];
    buffer.on("data", data => received.push(data));
    try {
      buffer.process(sequence.slice(0, -1));
      t.mock.timers.tick(75);
      assert.deepEqual(received, [], "an incomplete F2 must not be flushed before the SSH Escape timeout");
      buffer.process(sequence.slice(-1));
      assert.deepEqual(received, [sequence]);
      buffer.process("\x1b");
      t.mock.timers.tick(escapeTimeout);
      assert.deepEqual(received, [sequence, "\x1b"], "a standalone Escape still pauses promptly");
    } finally { buffer.destroy(); }
  }
});

test("real worker terminal isolates monitor refresh, command feedback and task cancellation", {
  timeout: 90_000,
}, async () => {
  await assertInstalledRuntime(packageRoot);
  await mkdir(TEST_ROOT, { recursive: true });
  const root = await mkdtemp(join(TEST_ROOT, "w-"));
  const socketRoot = join(TEST_SOCKET_ROOT, "w");
  await mkdir(socketRoot);
  const savedEnvironment = { ...process.env };
  let completed = false;
  let backend;
  let modelRequests = 0;
  let modelRequest;
  const modelServer = createServer((_request, response) => {
    let body = '';
    _request.on('data', chunk => { body += chunk; });
    _request.on('end', () => {
      modelRequest = JSON.parse(body);
      modelRequests++;
      response.writeHead(200, {'content-type':'text/event-stream'});
      response.write(`data: ${JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'fixture',
        choices:[{index:0,delta:{role:'assistant',content:'Local deterministic response'},finish_reason:null}]})}\n\n`);
    });
    // Keep this local stream open until the user aborts; no remote provider is used.
  });
  await new Promise(resolve => modelServer.listen(0, '127.0.0.1', resolve));
  try {
    process.env.CORAGENT_DEBUG = "1";
    process.env.CORAGENT_PI_DIAGNOSTIC_FILE = join(root, "pi-child.log");
    process.env.PI_CODING_AGENT_DIR = join(root, "agent");
    process.env.PI_AGENT_DIR = process.env.PI_CODING_AGENT_DIR;
    await mkdir(process.env.PI_CODING_AGENT_DIR);
    await writeFile(join(process.env.PI_CODING_AGENT_DIR, "models.json"), JSON.stringify({ providers: { fixture: {
      baseUrl: `http://127.0.0.1:${modelServer.address().port}/v1`, apiKey: "fixture-only", api: "openai-completions",
      models: [{id:"fixture", name:"Fixture", reasoning:false, input:["text"],
        cost:{input:0, output:0, cacheRead:0, cacheWrite:0}, contextWindow:1050000, maxTokens:128000}],
    } } }));
    process.env.CORAGENT_PYTHON = managedPython();
    process.env.PYTHONDONTWRITEBYTECODE = "1";
    const workspaceRoot = join(root, "workspaces");
    await mkdir(workspaceRoot);
    await execute(process.env.CORAGENT_PYTHON, [
      join(packageRoot, "apps/cli/workspace_mode.py"),
      "--root", join(workspaceRoot, "startup"), "--workspace-id", "startup",
    ]);
    const { createCoRAgentHarnessBackend } = await import(pathToFileURL(join(packageRoot, "apps/agent/runtime/backend.mjs")));
    backend = await createCoRAgentHarnessBackend({
      sourceRoot, packageRoot, workspaceRoot,
      serverDirectory: socketRoot, sessionDir: join(root, "sessions"),
      stateRoot: join(root, "state"), model: { provider: "fixture", id: "fixture" },
    });
    const created = await backend.createSession({ workspace_id: "startup", model: { provider: "fixture", id: "fixture" } });
    assert.equal(created.session.online, true);
    assert.equal(created.session.is_streaming, false);
    const read = await backend.readSession("startup", created.session.session_id);
    assert.equal(read.session.session_id, created.session.session_id);
    assert.equal(read.snapshot.operation, null);
    assert.ok(existsSync(join(root, "sessions", "startup", created.session.session_id, "session.sqlite")));
    const fromSource = (path) => import(pathToFileURL(join(sourceRoot, path)).href);
    const [{ createClientTui, runClientTui }, { startCoRAgentHost }, { connectHost }, { createTerminalSession, runTerminalSessions }] = await Promise.all([
      import(pathToFileURL(join(packageRoot,"apps/agent/terminal/tui.mjs"))),
      import(pathToFileURL(join(packageRoot,"apps/agent/host/server.mjs"))),
      import(pathToFileURL(join(packageRoot,"apps/agent/transport/host-client.mjs"))),
      import(pathToFileURL(join(packageRoot,"apps/agent/terminal/session.mjs"))),
    ]);
    const host = await startCoRAgentHost({socketPath:join(socketRoot,"host.sock"),workspaceRoot,stateRoot:join(root,"state"),sessionBackend:backend,monitorPollMs:0});
    const peers = new Set();
    const connect = async () => { const peer=await connectHost({socketPath:host.socketPath}); peers.add(peer); return peer; };
    const request = async (method,params) => {const peer=await connect();try{return await peer.request(method,params);}finally{peer.close();peers.delete(peer);}};
    const scope = {workspace_id:"startup",session_id:created.session.session_id};
    const query = (query,args) => request("session/query",{...scope,query,...(args===undefined?{}:{args})});
    let component;
    try {
      const prompt = await query("systemPrompt");
      assert.equal(prompt.workspace_id,"startup"); assert.equal(prompt.session_id,scope.session_id);
      assert.match(prompt.result.effective,/CoRAgent/); assert.ok(prompt.result.contributors.length>0);
      const telemetry = await query("telemetry");
      assert.equal(telemetry.result.inputBudgetTokens,917904); assert.equal(telemetry.result.estimated,true);
      assert.ok(telemetry.result.contextTokens>=0);
      assert.equal((await query("research","")).result.schema_version,"research-brief/1");
      assert.equal((await query("research","read")).result.schema_version,"research-search/2");
      assert.equal((await query("runtime")).scheduling,"running");
      await assert.rejects(request("session/retry",{...scope,request_id:"invalid-retry",task_id:"-1"}),{code:"invalid_task"});
      await assert.rejects(request("session/retry",{...scope,request_id:"missing-retry",task_id:"999999"}),{code:"task_not_retryable"});
      assert.match((await query("research","storage bootstrap")).error.message,/Usage/);
      assert.deepEqual((await backend.readSession("startup",scope.session_id)).snapshot.messages,read.snapshot.messages);
      const [{VirtualTerminal},{renderLayoutFrame}] = await Promise.all([
        fromSource("packages/tui/test/virtual-terminal.ts"),fromSource("packages/tui/src/layout.ts"),
      ]);
      const terminal = new VirtualTerminal(100,24);
      const lifetime = new AbortController();
      let quit=false,refreshMonitor,monitorRunning=1;
      const session=createTerminalSession({request,workspaceId:"startup",sessionId:scope.session_id,signal:lifetime.signal,
        quit(){quit=true;lifetime.abort();},switchSession(){throw new Error("Unexpected switch");}});
      session.monitor=async()=>({workspace_id:"startup",session_id:scope.session_id,task:null,
        jobs:{scope:"session",active:Array.from({length:monitorRunning},(_,i)=>({job_id:`job_${i}`,state:"running"})),counts:{running:monitorRunning,queued:0,total:monitorRunning},active_omitted:0},
        execution:{state:"idle"},continuation:{state:"idle"},updated_at:new Date().toISOString()});
      session.subscribeMonitor=callback=>{refreshMonitor=callback;return()=>{refreshMonitor=undefined;};};
      component=await createClientTui({session,request,connect,sourceRoot,terminal});
      const text=()=>stripVTControlCharacters(frame().lines.join("\n"));
      const frame=(width=100,height=24)=>renderLayoutFrame(component.layoutRoot,width,height,()=>{});
      const waitFor=async(predicate,timeout=4000)=>{
        for(let i=0;i<timeout/20;i++){if(await predicate())return;await new Promise(r=>setTimeout(r,20));}
        assert.fail(text());
      };
      const submit=value=>{terminal.sendInput("\x05");terminal.sendInput("\x15");terminal.sendInput(value);terminal.sendInput("\r");};
      const back=async()=>{terminal.sendInput("\x1b");await new Promise(r=>setImmediate(r));};
      const settle=()=>new Promise(r=>setTimeout(r,50));
      component.start();
      await waitFor(()=>!text().includes("Context: Unknown")&&text().includes("Monitor: Connected"));
      assert.equal(modelRequests,0);
      for(const command of ["usage","monitor","research","sys-prompt","model","thinking","tasks"]){
        submit(`/${command}`);
        await waitFor(()=>text().includes("Esc Back"));
        const focus=component.tui.getFocusedComponent();
        refreshMonitor();await settle();
        assert.equal(component.tui.getFocusedComponent(),focus);
        for(const [w,h] of [[100,24],[32,12],[20,10]])assert.equal(frame(w,h).lines.length,h);
        await back();
      }
      const wideText = () => stripVTControlCharacters(frame(140,32).lines.join("\n"));
      assert.match(wideText(),/Research & jobs/);
      assert.doesNotMatch(text(),/Research & jobs/);
      assert.equal(frame(140,32).primaryScrollView,frame().primaryScrollView);
      submit("/sidebar off");await waitFor(()=>!wideText().includes("Research & jobs"));await back();
      submit("/sidebar auto");await waitFor(()=>wideText().includes("Research & jobs"));await back();
      submit("/retry");await waitFor(()=>text().includes("No tasks are paused"));await back();
      await mkdir(join(workspaceRoot,"startup","outputs"),{recursive:true});
      await writeFile(join(workspaceRoot,"startup","outputs","plot.png"),Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=","base64"));
      submit("/image outputs/plot.png");await waitFor(()=>text().includes("Preview only"));
      assert.match(text(),/plot.png.*1×1/);
      await back();
      submit("/monitor");await waitFor(()=>text().includes("job_0 · running"));
      monitorRunning=2;refreshMonitor();await waitFor(()=>text().includes("job_1 · running"));
      await back();
      terminal.sendInput("draft text");terminal.sendInput("\x1b[D");terminal.sendInput("\x0c");
      await waitFor(()=>text().includes("Select model"));
      terminal.sendInput("ignored");await back();terminal.sendInput("!");
      assert.equal(component.editor.getText(),"draft tex!t");
      submit("/monitor task pause");await waitFor(()=>text().includes("Missing task ID"));
      assert.equal(component.editor.getText(),"/monitor task pause");
      for(const f2 of ["\x1bOQ","\x1b[12~"]){
        terminal.sendInput(f2);await waitFor(()=>text().includes("Command error"));
        assert.match(text(),/Usage:/);await back();
        // Restore the error after closing its details.
        submit("/monitor task pause");await waitFor(()=>text().includes("Missing task ID"));
      }
      let finishSlow,finishOperation,operationFinished=false;
      component.commands.replace({name:"slow",async run(_args,context){
        await new Promise(resolve=>{finishSlow=resolve;});
        await component.ui.showDocument({render:()=>["STALE DOCUMENT"],invalidate(){}},context);
        assert.equal(await component.ui.select("STALE SELECTOR",[{value:"stale",label:"stale"}],undefined,context),undefined);
        component.ui.showStatus("STALE STATUS",context);
      }});
      component.commands.replace({name:"delayed-operation",async run(_args,context){
        await new Promise(resolve=>{finishOperation=resolve;});operationFinished=true;
        component.ui.showStatus("STALE OPERATION",context,"success");
      }});
      submit("/slow");await waitFor(()=>typeof finishSlow==="function");await back();
      submit("/usage");await waitFor(()=>text().includes("Session usage"));finishSlow();await settle();
      assert.doesNotMatch(text(),/STALE/);await back();
      submit("/delayed-operation");await waitFor(()=>typeof finishOperation==="function");
      terminal.sendInput("working draft");await back();finishOperation();await waitFor(()=>operationFinished);
      assert.doesNotMatch(text(),/STALE/);assert.equal(component.editor.getText(),"working draft");
      submit("/thinking invalid");await waitFor(()=>text().includes("Unknown thinking level"));await back();
      submit("/model fixture/fixture");await waitFor(()=>text().includes("Selected fixture/fixture"));
      terminal.sendInput("timer draft");await waitFor(()=>!text().includes("Selected fixture/fixture"),4500);
      assert.equal(component.editor.getText(),"timer draft");
      submit("/thinking off");await waitFor(()=>text().includes("Thinking level: off"));await back();
      submit("/compact");await waitFor(()=>text().includes("Nothing to compact."));await back();
      submit("/reload");await waitFor(()=>text().includes("Reloaded model configuration"));await back();
      assert.equal(modelRequests,0);
      const pastedInput="请检查这份本地测试资料。\n"+"中文长消息与约束保持完整。".repeat(300);
      terminal.sendInput("\x05");terminal.sendInput("\x15");
      terminal.sendInput(`\x1b[200~${pastedInput}\x1b[201~`);
      assert.equal(component.editor.getExpandedText(),pastedInput);
      terminal.sendInput("\r");await waitFor(()=>modelRequests===1,10000);
      assert.ok(modelRequest.messages.some(message=>message.role==="user" && message.content===pastedInput));
      assert.ok(modelRequest.tools.some(tool=>tool.function.name==="task_read"));
      assert.ok(!modelRequest.tools.some(tool=>tool.function.name==="system_prompt"));
      assert.match(JSON.stringify(modelRequest.messages.filter(m=>m.role==="system")),/<available_skills>/);
      await waitFor(()=>text().includes("Working"),10000);
      const transcript=frame().primaryScrollView;
      submit("/sys-prompt");await waitFor(()=>text().includes("You are CoRAgent"));
      assert.equal(frame().primaryScrollView,undefined);await back();assert.equal(frame().primaryScrollView,transcript);
      assert.equal((await backend.readSession("startup",scope.session_id)).session.is_streaming,true);
      // Closing the terminal keeps the in-flight model request alive.
      component.close();component=undefined;
      assert.equal((await backend.readSession("startup",scope.session_id)).session.is_streaming,true);
      component=await createClientTui({session,request,connect,sourceRoot,terminal:new VirtualTerminal(100,24)});
      component.start();await waitFor(()=>text().includes("Working"));
      const persisted=await query("view");
      assert.equal(persisted.entries.flatMap(entry=>entry.model||[]).filter(message=>message.role==="user" &&
        JSON.stringify(message.content).includes("中文长消息与约束保持完整。")).length,1);
      component.tui.terminal.sendInput("\x1b");
      await waitFor(async()=>!(await backend.readSession("startup",scope.session_id)).session.is_streaming,10000);
      component.tui.terminal.sendInput("/quit");component.tui.terminal.sendInput("\r");await waitFor(()=>quit);
      component.close();component=undefined;
      await backend.createSession({workspace_id:"startup",session_id:"second",model:{provider:"fixture",id:"fixture"}});
      const opened=[];
      await runTerminalSessions({command:{sessionId:scope.session_id},workspaceId:"startup",request,createFacet:async session=>session,
        async run(command,options){
          opened.push(command.sessionId);
          const vt=new VirtualTerminal(100,24),session=options.facetLoader;
          const input=setTimeout(()=>{vt.sendInput(command.sessionId===scope.session_id?"/resume second":"/quit");vt.sendInput("\r");},300);
          const timeout=setTimeout(()=>session.quit(),5000);
          try {await runClientTui({session,request,connect,sourceRoot,terminal:vt});}
          finally {clearTimeout(input);clearTimeout(timeout);}
        },
      });
      assert.deepEqual(opened,[scope.session_id,"second"]);
      await assert.rejects(request("session/attach",{workspace_id:"startup",session_id:"missing"}),/not present/);
      assert.equal((await backend.listSessions("startup")).length,2);
      completed=true;
    } finally {component?.close();for(const peer of peers)peer.close();await host.close();}
  } finally {
    await backend?.close();
    modelServer.closeAllConnections();await new Promise(resolve=>modelServer.close(resolve));
    for(const key of Object.keys(process.env))if(!(key in savedEnvironment))delete process.env[key];
    Object.assign(process.env,savedEnvironment);
    if(!completed)await retainPiDiagnostics(socketRoot,join(root,"pi-diagnostics"));
    if(completed)await rm(root,{recursive:true,force:true});
    await rm(socketRoot,{recursive:true,force:true});
  }
});
