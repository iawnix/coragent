import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { TEST_ROOT, managedPython } from "./test-environment.mjs";
import { create_workspace_initializer } from "../../../apps/agent/host/workspace.mjs";
import { create_python_runtime_bridge, create_query_runtime_bridge } from "../../../apps/agent/bridge/client.mjs";

async function workspace(t) {
  const root = await mkdtemp(join(TEST_ROOT, "query-worker-"));
  const workspaceRoot = join(root, "workspace"), workspaceId = "query-isolation";
  t.after(() => rm(root, { recursive: true, force: true }));
  const initializer = create_workspace_initializer();
  await initializer.initialize_workspace({ workspace_root: workspaceRoot, workspace_id: workspaceId });
  await initializer.admit_workspace(workspaceRoot);
  return { workspace_root: workspaceRoot, workspace_id: workspaceId };
}

test("the independent query worker reads research committed by the execution worker", { timeout: 15000 }, async t => {
  const options = await workspace(t);
  const execution = create_python_runtime_bridge(options), query = create_query_runtime_bridge(options);
  try {
    const created = await execution.execute_command("research_create", { goal: "Which boundary condition is valid?",
      plan: "Compare the retained evidence.", request_id: "query-visible-write" });
    const result = await query.execute_command("research_read", {});
    assert.deepEqual(result.nodes.map(node => node.id), [created.node.id]);
    assert.equal(result.nodes[0].goal, created.node.goal);
    assert.equal((await query.execute_command("job_list", {})).jobs.length, 0);
  } finally {
    await Promise.all([execution.close(), query.close()]);
  }
});

const delayedMutation = `
import json, sys
from pathlib import Path
from research_agent.foundation.transactions import workspace_transaction, write_json
from research_agent.research.nodes import create

@workspace_transaction('test.query_atomic')
def mutate(root, request):
    created = create(root, {'goal': 'A jointly committed research question', 'plan': 'Inspect both Job observations.'})
    write_json(root / 'operations/executions/job_1.json', {'job_id': 'job_1', 'state': 'succeeded'})
    print('staged', flush=True)
    if sys.stdin.readline().strip() != 'commit':
        raise RuntimeError('fixture commit was not released')
    write_json(root / 'operations/executions/job_2.json', {'job_id': 'job_2', 'state': 'failed'})
    return created

result = mutate(Path(sys.argv[1]), {'request_id': 'query-atomic-write'})
print(json.dumps({'node_id': result['node']['id']}), flush=True)
`;

test("research and Job queries wait for another process to commit its complete workspace transaction", { timeout: 15000 }, async t => {
  const options = await workspace(t);
  const research = create_query_runtime_bridge(options), jobs = create_query_runtime_bridge(options);
  let writer, closed, stderr = "";
  try {
    // Warm both processes before taking the lock so a slow process launch
    // cannot masquerade as a correctly blocked read.
    await Promise.all([research.execute_command("research_read", {}), jobs.execute_command("job_list", {})]);
    writer = spawn(managedPython(), ["-B", "-u", "-c", delayedMutation, options.workspace_root], {
      cwd: TEST_ROOT, env: process.env, stdio: ["pipe", "pipe", "pipe"],
    });
    closed = once(writer, "close");
    closed.catch(() => {});
    writer.stderr.setEncoding("utf8");
    writer.stderr.on("data", data => { stderr += data; });
    const [ready] = await once(writer.stdout, "data", { signal: AbortSignal.timeout(5000) });
    assert.equal(ready.toString().trim(), "staged", stderr);
    let researchSettled = false, jobsSettled = false;
    const reading = research.execute_command("research_read", {}).then(value => { researchSettled = true; return value; });
    const listing = jobs.execute_command("job_list", {}).then(value => { jobsSettled = true; return value; });
    const observed = Promise.all([reading, listing]);
    observed.catch(() => {});
    await delay(100);
    assert.equal(researchSettled, false, "research read must wait for the transaction lock");
    assert.equal(jobsSettled, false, "Job list must wait for the transaction lock");
    writer.stdin.end("commit\n");
    const [snapshot, page] = await observed;
    assert.equal(snapshot.nodes.length, 1);
    assert.equal(snapshot.nodes[0].goal, "A jointly committed research question");
    assert.deepEqual(page.jobs.map(({ job_id, state }) => ({ job_id, state })), [
      { job_id: "job_1", state: "succeeded" }, { job_id: "job_2", state: "failed" },
    ]);
    const [code] = await closed;
    assert.equal(code, 0, stderr);
  } finally {
    if (writer?.exitCode === null) writer.kill("SIGTERM");
    if (closed) await closed;
    await Promise.all([research.close(), jobs.close()]);
  }
});
