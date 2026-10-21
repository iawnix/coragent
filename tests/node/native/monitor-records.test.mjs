import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { createJobEvents } from "../../../apps/agent/host/jobs/events.mjs";
import { TEST_ROOT, managedPython } from "./test-environment.mjs";

const exec = promisify(execFile);

test("Host relays current Monitor records and rejects invalid formats and mismatched bindings", async t => {
  const root = await mkdtemp(join(TEST_ROOT, "monitor-records-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await exec(managedPython(), ["-B", "-c", `
import sys
from pathlib import Path
from research_agent.research.workspace import initialize_workspace, admit_research_workspace
from research_agent.application.job_manager import bind
root = Path(sys.argv[1])
initialize_workspace(root, 'monitor_records', 'research')
admit_research_workspace(root)
bind(root, {'job_id': 'job_1', 'user_task_id': 'task_1'}, 'session_1')
`, root]);
  const directory = join(root, "operations/monitors", (await readdir(join(root, "operations/monitors")))[0]);
  const bindingPath = join(directory, "binding.json");
  const binding = JSON.parse(await readFile(bindingPath, "utf8"));
  const eventsRoot = join(directory, "events");
  await mkdir(eventsRoot, { recursive: true });
  const eventPath = join(eventsRoot, "event_1.json");
  const event = { ...binding, schema_version: "coragent-job-monitor-event/2", event_id: "event_1",
    sequence: 1, state: "failed", last_state: "failed", previous_state: null,
    status_digest: `sha256:${"b".repeat(64)}`, program_status: null, exit_status: 1,
    error_class: null, error: null, observed_at: "2026-10-21T00:00:00Z", status: { state: "failed" } };

  async function scan(bindingValue, eventValue) {
    await writeFile(bindingPath, JSON.stringify(bindingValue));
    await writeFile(eventPath, JSON.stringify(eventValue));
    const notices = [];
    const scanner = createJobEvents({ epoch: "test", listWorkspaces: async () => [{ root, workspace_id: "monitor_records" }],
      clients: [{ monitorWorkspaces: new Set(["monitor_records"]), peer: { notify: (...args) => notices.push(args), close() {} } }] });
    try { await scanner.pollMonitors(); } finally { scanner.stop(); }
    return notices;
  }

  assert.equal((await scan(binding, event)).length, 1);
  for (const extra of [{ enabled: true }, { enabled: false }, { unexpected: "field" }]) {
    assert.equal((await scan({ ...binding, ...extra }, event)).length, 0);
    assert.equal((await scan(binding, { ...event, ...extra })).length, 0);
  }
  const missingTask = { ...binding }; delete missingTask.user_task_id;
  assert.equal((await scan(missingTask, event)).length, 0);
  assert.equal((await scan(binding, { ...event, user_task_id: "task_2" })).length, 0);
  assert.equal((await scan(binding, { ...event, node_id: "node_1", node_revision: null })).length, 0);
  assert.equal((await scan(binding, { ...event, sequence: 0 })).length, 0);
  assert.equal((await scan(binding, { ...event, schema_version: "unsupported" })).length, 0);
});
