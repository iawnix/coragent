import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { mkdir, mkdtemp, rm, writeFile, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { TEST_ROOT, TEST_SOCKET_ROOT, managedPython, pinnedPiSource, assertInstalledRuntime } from "./test-environment.mjs";

const execute = promisify(execFile);
const packageRoot = resolve(process.env.CORAGENT_TEST_PACKAGE_ROOT || process.cwd());

for (const scenario of ["single", "branches", "block-resume", "execution-recovery", "delivery-recovery", "user-stop"]) test(`real Worker continues ${scenario} research after a partial answer and completes one durable delivery`, { timeout: 60_000 }, async () => {
  await assertInstalledRuntime(packageRoot);
  const root = await mkdtemp(join(TEST_ROOT, "task-flow-"));
  const socketRoot = join(TEST_SOCKET_ROOT, "t");
  await mkdir(socketRoot);
  const saved = { ...process.env };
  let backend, server, requests = 0, fixtureError, failureRequests = 0, recoveryRestarted = false, blockedWrite = false;
  let scope, assessmentPending = false;
  const blockedStopCalls = new Set();
  const observedRequests = [];
  const tools = [];
  try {
    const agentDir = join(root, "agent"), workspaceRoot = join(root, "workspaces");
    await mkdir(agentDir); await mkdir(workspaceRoot);
    Object.assign(process.env, { PI_CODING_AGENT_DIR: agentDir, PI_AGENT_DIR: agentDir,
      CORAGENT_PYTHON: managedPython(), PYTHONDONTWRITEBYTECODE: "1",
      CORAGENT_TASK_RECOVERY_BASE_DELAY_MS: "500", CORAGENT_TASK_RECOVERY_MAX_DELAY_MS: "500" });
    const jobConfig = join(root, "job.toml");
    await writeFile(jobConfig, '[execution]\ndefault_target="local"\n[execution.targets.local]\ntype="local"\ndriver="process"\nsupervisor="process"\n');
    process.env.CORAGENT_JOB_CONFIG = jobConfig;
    await execute(managedPython(), [join(packageRoot, "apps/agent-cli/workspace_mode.py"),
      "--root", join(workspaceRoot, "task-flow"), "--workspace-id", "task-flow"]);
    server = createServer(async (req, res) => {
      try {
        let body = ""; for await (const part of req) body += part;
        const request = JSON.parse(body);
        // Review synthesis is an internal tool-free request and must not
        // consume one of the continuation fixture's scripted steps.
        if (JSON.stringify(request).includes('deterministic brief')) {
          const response = { id: `review_${observedRequests.length}`, object: "chat.completion",
            choices: [{ index: 0, message: { role: "assistant", content: JSON.stringify({
              status: "uncertain", summary: "Inspect the recorded research evidence.",
              key_findings: [], contradictions: [], uncertainties: [], next_actions: [], source_refs: [],
            }) }, finish_reason: "stop" }] };
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify(response));
          return;
        }
        observedRequests.push(request);
        if (scenario === "user-stop" && requests === 4) {
          await backend.sendInput({ ...scope, client_message_id: "stop-research", request_id: "stop-research",
            text: "Stop this research and cancel its running calculations.", mode: "steer" });
        }
        if (failureRequests === 0 && ((scenario === "execution-recovery" && requests === 4)
          || (scenario === "delivery-recovery" && requests === 7))) {
          failureRequests++;
          res.writeHead(503, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: { message: "503 Service Unavailable", type: "server_error" } }));
          return;
        }
        const results = request.messages.filter(message => message.role === "tool").map(message => {
          if (scenario === "delivery-recovery" && message.content.includes("Delivery recovery permits read-only tools")) {
            blockedWrite = true; return null;
          }
          if (scenario === "user-stop" && message.content.includes("The user stopped this task.")) {
            blockedStopCalls.add(message.tool_call_id); return null;
          }
          assert.match(message.content, /^\s*[\[{]/, `fixture tools must return their structured success result: ${message.content}`);
          return JSON.parse(message.content);
        }).filter(Boolean);
        const envelope = request.messages.findLast(message =>
          typeof message.content === "string" && message.content.startsWith('<runtime_control origin="runtime">'));
        assert.ok(envelope, "every request must carry runtime context at the tail");
        const taskContext = JSON.parse(envelope.content.split("\n")[1]);
        const task = taskContext.task;
        const node = results.find(result => result?.node)?.node;
        const result = results.find(result => result?.result)?.result;
        const userIds = taskContext.actual_user_submission_ids;
        const latestNodes = new Map(results.filter(result => result?.node).map(result => [result.node.title, result.node]));
        const published = new Map(results.filter(result => result?.result).map(result => [result.result.conclusion, result.result]));
        const rootNode = latestNodes.get("Compare derivations"), shared = latestNodes.get("Approximation bounds");
        const branchA = latestNodes.get("Derivation A"), branchB = latestNodes.get("Derivation B");
        const researchEnvelope = request.messages.findLast(message => typeof message.content === "string" && message.content.startsWith('<research_context origin="runtime">'));
        const researchPayload = JSON.parse(researchEnvelope.content.split("\n")[1]);
        const snapshot = researchPayload.research_brief;
        assert.ok(snapshot && snapshot.schema_version === "research-brief/1");
        if (node && task && requests === 2) {
          assert.deepEqual(snapshot.scope.entry_node_ids, [node.id]);
          assert.deepEqual(snapshot.scope.focus_node_ids, [node.id]);
          assert.equal(task.revision, 1);
          assert.ok(researchPayload.task.initial_plan && researchPayload.task.next_action);
        }
        if (snapshot.scope.focus_node_ids?.length) {
          assert.ok(snapshot.findings.some(item => snapshot.scope.focus_node_ids.includes(item.ref)));
        }
        if (scenario === "branches" && snapshot.scope.entry_node_ids?.length) {
          assert.ok(snapshot.source_refs.includes(rootNode.id));
          if (snapshot.scope.focus_node_ids.includes(branchA?.id)) assert.ok(snapshot.source_refs.includes(branchA.id));
        }
        const bind = (entry, focus) => ({ name: "task_update", arguments: { expected_revision: task?.revision,
          action: "set_research", research: { entry_node_ids: entry, focus_node_ids: focus } } });
        const singleSteps = [
          { name: "task_begin", arguments: { title: "Fixture research", objective: "Record a reproducible fixture finding without external delivery.",
            source_submission_ids: userIds, criteria: [{ id: "finding", description: "Publish the fixture finding and report it." }],
            initial_plan: "Create the fixture Node, record the finding and deliver the evidence-backed result.",
            next_action: "Create the fixture research Node." } },
          { name: "research_create", arguments: { goal: "Verify continued analysis", plan: "Record a local deterministic observation." } },
          { name: "task_read", arguments: {} },
          "Initial analysis is ready; the finding still needs to be recorded.",
          { name: "task_read", arguments: {} },
          { name: "research_result", arguments: { node_id: node?.id, conclusion: "The local fixture completed its analysis.", limitations: "Deterministic fixture only." } },
          { name: "task_update", arguments: { expected_revision: task?.revision, action: "propose_completion",
            completion: [{ criterion_id: "finding", evidence_refs: [result?.id] }] } },
          "The fixture finding is recorded. Research is complete.",
        ];
        const negative = published.get("Derivation A violates the stated boundary condition.");
        const provisional = published.get("Derivation B satisfies the boundary condition at leading order.");
        const corrected = published.get("Derivation B remains valid with the next-order correction.");
        const bounds = published.get("The approximation has a bounded second-order remainder.");
        const synthesis = published.get("The comparison supports derivation B within the approximation bounds.");
        const branchSteps = [
          { name: "task_begin", arguments: { title: "Compare derivations", objective: "Compare independent derivations and retain their limitations without external delivery.",
            source_submission_ids: userIds, criteria: [{ id: "comparison", description: "Retain both findings, approximation bounds and the comparison." }],
            initial_plan: "Create the comparison and bounds Nodes, test both derivations, and publish the supported comparison with limitations.",
            next_action: "Create the comparison root Node." } },
          { name: "research_create", arguments: { title: "Compare derivations", goal: "Which derivation satisfies the boundary condition?", plan: "Compare independent candidates against shared approximation bounds." } },
          { name: "research_create", arguments: { title: "Approximation bounds", goal: "What is the approximation error?", plan: "Bound the neglected terms." } },
          { name: "research_create", arguments: { title: "Derivation A", goal: "Does derivation A satisfy the boundary condition?", plan: "Substitute at the boundary.",
            relations: [{ kind: "part_of", target: rootNode?.id }, { kind: "requires", target: shared?.id }] } },
          { name: "research_create", arguments: { title: "Derivation B", goal: "Does derivation B satisfy the boundary condition?", plan: "Evaluate the boundary and next-order correction.",
            relations: [{ kind: "part_of", target: rootNode?.id }, { kind: "requires", target: shared?.id }, { kind: "alternative_to", target: branchA?.id }] } },
          bind([rootNode?.id, shared?.id], [branchA?.id, branchB?.id]),
          { name: "research_result", arguments: { node_id: branchA?.id, conclusion: "Derivation A violates the stated boundary condition.", as_assessment: true } },
          { name: "research_update", arguments: { node_id: branchA?.id, note: "End this route after the boundary counterexample; derivation B remains to be checked.", status: "closed" } },
          "Derivation A fails the boundary condition. Derivation B and the comparison remain unfinished.",
          { name: "task_read", arguments: {} },
          { name: "research_result", arguments: { node_id: branchB?.id, conclusion: "Derivation B satisfies the boundary condition at leading order.", as_assessment: true } },
          { name: "research_result", arguments: { node_id: shared?.id, conclusion: "The approximation has a bounded second-order remainder." } },
          bind([rootNode?.id, shared?.id], [branchB?.id, rootNode?.id]),
          { name: "research_result", arguments: { node_id: branchB?.id, conclusion: "Derivation B remains valid with the next-order correction.", supersedes: provisional?.id, inputs: [bounds?.id], as_assessment: true } },
          { name: "research_result", arguments: { node_id: rootNode?.id, conclusion: "The comparison supports derivation B within the approximation bounds.",
            inputs: [negative?.id, corrected?.id, bounds?.id], limitations: "Synthetic deterministic derivations; this tests research orchestration, not a scientific result." } },
          { name: "task_update", arguments: { expected_revision: task?.revision, action: "propose_completion",
            completion: [{ criterion_id: "comparison", evidence_refs: [synthesis?.id] }] } },
          "Both derivations and the approximation bounds are retained. The comparison is complete.",
        ];
        const blockSteps = [
          ...singleSteps.slice(0, 5),
          { name: "task_update", arguments: { expected_revision: task?.revision, action: "block",
            block_kind: "missing_user_input", resume_when: "The user supplies the required boundary value.",
            reason: "The required boundary value is missing; independent analysis is exhausted. Supply the boundary value to resume." } },
          "Research is blocked pending the required boundary value.",
          { name: "task_update", arguments: { expected_revision: task?.revision, action: "refine", source_submission_ids: userIds } },
          ...singleSteps.slice(5),
        ];
        const deliverySteps = [...singleSteps.slice(0, 7),
          { name: "bash", arguments: { command: "touch forbidden-delivery-write" } }, singleSteps[7]];
        const stopSteps = [...singleSteps.slice(0, 5),
          { name: "task_update", arguments: { expected_revision: task?.revision, action: "apply_user_control",
            control: "cancel", jobs: "cancel", source_submission_ids: userIds } },
          { name: "bash", arguments: { command: "touch forbidden-stop-write" } },
          singleSteps[0],
          { name: "task_read", arguments: {} },
          "Research is cancelled. No further analysis or calculations will be launched.",
        ];
        const steps = scenario === "user-stop" ? stopSteps : scenario === "branches" ? branchSteps : scenario === "block-resume" ? blockSteps
          : scenario === "delivery-recovery" ? deliverySteps : singleSteps;
        let step = steps[requests++];
        let insertedAssessment = false;
        if (step?.arguments?.action === "propose_completion") {
          if (!assessmentPending) {
            const item = step.arguments.completion[0];
            step = { name: "artifact_create", arguments: { name: "task-assessment.json", media_type: "application/json",
              content: JSON.stringify({ schema_version: "task-assessment/1", workspace_id: "task-flow",
                user_task_id: task.user_task_id, requirements_revision: task.requirements_revision,
                criterion_id: item.criterion_id, status: "met", reason: "Requested fixture finding retained", conflicts: [],
                checks: [{ method: "reasoned", status: "met", reason: "Requested finding and limitations inspected", evidence_refs: item.evidence_refs }] }) } };
            requests--; assessmentPending = true; insertedAssessment = true;
          } else {
            const artifact = results.findLast(value => value?.artifact_id);
            assert.ok(artifact?.artifact_id);
            step.arguments.completion_outcome = "full";
            step.arguments.completion[0].status = "met";
            step.arguments.completion[0].assessment_ref = artifact.artifact_id;
            assessmentPending = false;
          }
        }
        assert.ok(step, "completed research must not trigger another model request");
        if (typeof step !== "string") tools.push(step.name);
        const delta = typeof step === "string" ? { role: "assistant", content: step } : {
          role: "assistant", tool_calls: [{ index: 0, id: `task_call_${requests}${insertedAssessment ? "_assessment" : ""}`, type: "function",
            function: { name: step.name, arguments: JSON.stringify(step.arguments) } }],
        };
        res.writeHead(200, { "content-type": "text/event-stream" });
        for (const [value, finish_reason] of [[delta, null], [{}, typeof step === "string" ? "stop" : "tool_calls"]]) {
          res.write(`data: ${JSON.stringify({ id: `reply_${requests}`, object: "chat.completion.chunk", created: 1,
            model: "fixture", choices: [{ index: 0, delta: value, finish_reason }] })}\n\n`);
        }
        res.end("data: [DONE]\n\n");
      } catch (error) {
        fixtureError = error;
        res.writeHead(500); res.end("deterministic fixture failed");
      }
    });
    await new Promise(done => server.listen(0, "127.0.0.1", done));
    await writeFile(join(agentDir, "models.json"), JSON.stringify({ providers: { fixture: {
      baseUrl: `http://127.0.0.1:${server.address().port}/v1`, apiKey: "fixture-only", api: "openai-completions",
      models: [{ id: "fixture", name: "Fixture", reasoning: false, input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 200000, maxTokens: 4096 }],
    } } }));
    await writeFile(join(agentDir, "settings.json"), JSON.stringify({ retry: { enabled: false } }));
    const { createCoRAgentHarnessBackend } = await import(pathToFileURL(join(packageRoot, "apps/agent/pi/backend.mjs")));
    const options = { sourceRoot: pinnedPiSource(), packageRoot, workspaceRoot,
      serverDirectory: socketRoot, sessionDir: join(root, "sessions"), stateRoot: join(root, "state"),
      model: { provider: "fixture", id: "fixture" } };
    await assert.doesNotReject(async () => { backend = await createCoRAgentHarnessBackend(options); });
    let created;
    await assert.doesNotReject(async () => { created = await backend.createSession({ workspace_id: "task-flow", model: { provider: "fixture", id: "fixture" } }); });
    scope = { workspace_id: "task-flow", session_id: created.session.session_id };
    await backend.sendInput({ ...scope, client_message_id: "start-fixture-task", request_id: "start-fixture-task",
      text: "Perform the local fixture research and report the completed finding. Do not send anything externally.", mode: "auto" });
    let overview;
    if (scenario === "block-resume") {
      let blockedRuns;
      for (let attempt = 0; attempt < 200; attempt++) {
        assert.ifError(fixtureError);
        overview = await backend.monitor("monitor/overview", scope);
        if (overview.task?.state === "blocked" && requests === 7) {
          blockedRuns = await backend.monitor("monitor/runs", { ...scope, user_task_id: overview.task.user_task_id });
          if (blockedRuns.items.length === 2 && blockedRuns.items.every(run => run.state === "done")) break;
        }
        await new Promise(done => setTimeout(done, 100));
      }
      assert.equal(overview.task?.state, "blocked");
      assert.equal(requests, 7, "automatic block must deliver its final explanation");
      assert.ok(blockedRuns?.items.every(run => run.state === "done"), "block explanation must finish delivery before restart");
      for (const run of blockedRuns.items) {
        const detail = await backend.monitor("monitor/run/read", { ...scope, run_id: run.run_id });
        assert.ok(detail.items.every(item => item.error === null));
      }
      await backend.close(); backend = await createCoRAgentHarnessBackend(options);
      assert.equal((await backend.monitor("monitor/overview", scope)).task.state, "blocked");
      await new Promise(done => setTimeout(done, 150));
      assert.equal(requests, 7, "restart must not resume a blocked task");
      await backend.sendInput({ ...scope, client_message_id: "resolve-blocker", request_id: "resolve-blocker",
        text: "Use boundary value zero and continue the research to completion.", mode: "auto" });
    }
    for (let attempt = 0; attempt < 200; attempt++) {
      assert.ifError(fixtureError);
      await assert.doesNotReject(async () => { overview = await backend.monitor("monitor/overview", scope); });
      if (scenario.endsWith("-recovery") && overview.task?.execution_recovery?.state === "retrying" && !recoveryRestarted) {
        assert.equal((await backend.monitor("monitor/task/read", { ...scope, user_task_id: overview.task.user_task_id })).task.execution_recovery.failures, 1);
        assert.equal(overview.task.state, scenario === "delivery-recovery" ? "completing" : "active");
        await backend.close(); backend = await createCoRAgentHarnessBackend(options); recoveryRestarted = true;
      }
      if (overview.task?.state === "completed") break;
      if (scenario === "user-stop" && overview.task?.state === "cancelled" && requests === 10) {
        const runs = await backend.monitor("monitor/runs", { ...scope, user_task_id: overview.task.user_task_id });
        if (runs.items.every(run => run.state === "done")) break;
      }
      await new Promise(done => setTimeout(done, 100));
    }
    if (scenario === "user-stop") {
      assert.equal(overview.task?.state, "cancelled");
      assert.equal(requests, 10, "the stopped run must finish its acknowledgement");
      assert.equal(blockedStopCalls.size, 2, "both shell work and replacement tasks are blocked");
      await assert.rejects(readFile(join(workspaceRoot, "task-flow", "forbidden-stop-write")), { code: "ENOENT" });
      const runs = await backend.monitor("monitor/runs", { ...scope, user_task_id: overview.task.user_task_id });
      assert.ok(runs.items.every(run => run.state === "done"));
      const stoppedId = overview.task.user_task_id;
      await backend.close(); backend = await createCoRAgentHarnessBackend(options);
      for (let attempt = 0; attempt < 3; attempt++) {
        const restored = await backend.monitor("monitor/overview", scope);
        assert.equal(restored.task.user_task_id, stoppedId);
        assert.equal(restored.task.state, "cancelled");
        await new Promise(done => setTimeout(done, 100));
      }
      assert.equal(requests, 10, "restart and Monitor queries must not resume cancelled research");
      return;
    }
    assert.equal(overview.task?.state, "completed");
    assert.equal(requests, scenario === "branches" ? 17 : scenario === "block-resume" ? 11 : scenario === "delivery-recovery" ? 9 : 8);
    if (scenario.endsWith("-recovery")) {
      assert.equal(failureRequests, 1); assert.equal(recoveryRestarted, true);
      assert.equal(overview.task.execution_recovery, null);
      assert.equal(tools.filter(name => name === "research_result").length, 1, "recovery must not repeat the completed evidence write");
      if (scenario === "delivery-recovery") {
        assert.equal(blockedWrite, true);
        await assert.rejects(readFile(join(workspaceRoot, "task-flow", "forbidden-delivery-write")), { code: "ENOENT" });
      }
    }
    if (scenario === "single") assert.deepEqual(tools, ["task_begin", "research_create", "task_read", "task_read", "research_result", "artifact_create", "task_update"]);
    else if (scenario === "branches") assert.equal(tools.filter(name => name === "research_create").length, 4);
    assert.equal(overview.jobs.counts.total, 0, "continued analysis must not require a compute event");
    const runs = await backend.monitor("monitor/runs", { ...scope, user_task_id: overview.task.user_task_id });
    assert.equal(runs.items.length, scenario === "block-resume" || scenario.endsWith("-recovery") ? 3 : 2);
    assert.deepEqual(new Set(runs.items.map(run => run.producer)), new Set(["user", "task_controller"]));
    for (const run of runs.items) {
      const detail = { items: [] }; let cursor;
      do {
        const page = await backend.monitor("monitor/run/read", { ...scope, run_id: run.run_id, limit: 100, ...(cursor ? { cursor } : {}) });
        detail.items.push(...page.items); cursor = page.next_cursor;
      } while (cursor);
      if (scenario.endsWith("-recovery")) {
        if (run.state === "unanswered") {
          assert.ok(run.generation_count > 0, "failed run has an indexed generation");
          assert.ok(detail.items.length > 0, "failed run records survive restart");
          assert.ok(detail.items.some(item => item.kind === "pi.generation"), "failed generation is visible");
        } else if (run.producer === "user") {
          assert.ok(detail.items.some(item => item.kind === "pi.generation"), "initial user generation survives restart");
          assert.ok(detail.items.some(item => item.kind === "pi.tool"), "initial user tools survive restart");
        } else {
          assert.ok(detail.items.some(item => item.kind === "pi.generation"), "recovery generation is visible");
          assert.ok(detail.items.some(item => item.kind === "pi.tool"), "recovery tools are visible");
        }
      } else assert.ok(detail.items.some(item => item.kind === "pi.generation"));
      if (run.state === "unanswered") {
        assert.ok(scenario.endsWith("-recovery"));
        assert.ok(detail.items.some(item => item.error !== null));
        continue;
      }
      assert.ok(detail.items.some(item => item.kind === "pi.tool"));
      assert.ok(detail.items.some(item => item.kind === "pi.tool" && tools.includes(item.tool_name)));
      if (scenario !== "delivery-recovery") assert.ok(detail.items.every(item => item.error === null), "successful research has no execution errors");
    }
    const count = requests;
    const research = await backend.monitor("monitor/task/read", { ...scope, user_task_id: overview.task.user_task_id });
    assert.deepEqual(research.research.research.entry_node_ids, research.task.research.entry_node_ids);
    if (scenario === "branches") {
      assert.equal(research.research.research.nodes.find(node => node.title === "Derivation A").status, "closed");
      assert.equal(research.research.research.nodes.find(node => node.title === "Approximation bounds").status, "open", "completing a task leaves shared research open");
    }
    await backend.close(); backend = await createCoRAgentHarnessBackend(options);
    const restored = await backend.monitor("monitor/overview", scope);
    assert.equal(restored.task.state, "completed");
    assert.equal(restored.task.user_task_id, overview.task.user_task_id);
    assert.deepEqual((await backend.monitor("monitor/task/read", { ...scope, user_task_id: restored.task.user_task_id })).task.research, research.task.research, "restart retains the same research identities");
    await new Promise(done => setTimeout(done, 100));
    assert.equal(requests, count, "restart and read-only Monitor queries cannot repeat delivery");
    const objective = scenario !== "branches" ? "Record a reproducible fixture finding" : "Compare independent derivations";
    assert.ok(observedRequests.slice(3).every(request => JSON.stringify(request.messages).includes(objective)));
  } finally {
    try { await backend?.close(); }
    finally {
      if (server) { server.closeAllConnections(); await new Promise(done => server.close(done)); }
      for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
      Object.assign(process.env, saved);
      await rm(socketRoot, { recursive: true, force: true });
      await rm(root, { recursive: true, force: true });
    }
  }
});
