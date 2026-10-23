import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  deliverJobEvent,
  parseJobWorkerArguments,
  runJobWorkerLoops,
} from "../../../apps/agent/host/jobs/worker.mjs";
import { createObservationScheduler, firstSessionBatches } from "../../../apps/agent/host/jobs/scheduling.mjs";
import { JOB_EVENT_IDS_LIMIT } from "../../../apps/agent/contracts/monitor.mjs";
import { create_workspace_initializer } from "../../../apps/agent/host/workspace.mjs";

async function fixture(t) {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "t-"));
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }));
  const workspace = join(temporaryRoot, "ts_001");
  const canonicalId = "ws_" + "a".repeat(24);
  const initializer = create_workspace_initializer();
  await initializer.initialize_workspace({ workspace_root: workspace, workspace_id: canonicalId, workspace_mode: "research" });
  await initializer.admit_workspace(workspace);
  const event = { event_id: "evt_1", monitor_id: "mon_1", workspace_id: canonicalId, node_id: "node_1", job_id: "job_1", node_revision: 1, state: "succeeded" };
  const delivery = { event_id: event.event_id, session_id: "existing-session", request_id: "monitor:evt_1" };
  const completed = new Set();
  const receipts = [];
  return { workspace, canonicalId, event, delivery, completed, receipts,
    async runJson(command, _workspace, args) {
      assert.equal(args[args.indexOf("--request-id") + 1], delivery.request_id);
      const channel = args[args.indexOf("--channel") + 1];
      if (command === "claim") return { ...delivery, claimed: !completed.has(channel), claim_token: `token-${channel}`,
        batch_event_ids: [event.event_id], events: [event] };
      assert.equal(command, "complete");
      assert.equal(args[args.indexOf("--claim-token") + 1], `token-${channel}`);
      const delivered = args.includes("--delivered");
      receipts.push({ channel, delivered });
      if (delivered) completed.add(channel);
      return {};
    },
  };
}

test("monitor only wakes the owning session and never sends mail", async (t) => {
  const state = await fixture(t);
  const wakes = [];
  let notifications = 0;
  const dependencies = { ...state,
    async sendWake(params) { wakes.push(params); return { accepted: true }; },
    async sendNotification() { notifications++; },
  };
  assert.deepEqual(await deliverJobEvent(dependencies), []);
  assert.deepEqual(await deliverJobEvent(dependencies), []);
  assert.equal(wakes.length, 1);
  assert.equal(notifications, 0);
  assert.equal(wakes[0].session_id, "existing-session");
  assert.equal(wakes[0].mode, "next_run");
  assert.deepEqual(wakes[0].event_ids, [state.event.event_id]);
  assert.equal(wakes[0].text, undefined);
});

test("an offline session leaves wake retryable", async (t) => {
  const state = await fixture(t);
  const errors = await deliverJobEvent({ ...state,
    async sendWake() { throw Object.assign(new Error("session offline"), { code: "session_offline", retryable: true }); },
    async sendNotification() {},
  });
  assert.deepEqual(errors, ["wake: session offline"]);
  assert.deepEqual([...state.completed], []);
  assert.deepEqual(state.receipts, [{ channel: "wake", delivered: false }]);
});

test("busy wake remains undelivered and retryable without a research-state token", async (t) => {
  const state = await fixture(t);
  const errors = await deliverJobEvent({ ...state,
    sendWake: async () => ({ accepted: false, error: { code: "busy" } }),
  });
  assert.deepEqual(errors, []);
  assert.deepEqual(state.receipts, [{ channel: "wake", delivered: false }]);
});

test("an uncertain Host wake remains retryable", async (t) => {
  const state = await fixture(t);
  const errors = await deliverJobEvent({ ...state,
    async sendWake() { return { accepted: true, state: "uncertain" }; },
    async sendNotification() {},
  });
  assert.deepEqual(errors, ["wake: Host returned an uncertain monitor wake"]);
  assert.deepEqual(state.receipts, [{ channel: "wake", delivered: false }]);
});

test("managed monitor options require a Host endpoint", () => {
  assert.deepEqual(parseJobWorkerArguments(["--workspace-root", "/workspaces", "--host-socket", "/state/host.sock", "--state-root", "/state", "--interval-ms=1000", "--once"]), {
    workspaceRoot: "/workspaces", hostSocket: "/state/host.sock", stateRoot: "/state", intervalMs: 1000, once: true,
  });
  assert.throws(() => parseJobWorkerArguments(["--workspace-root", "/workspaces"]), /host-socket/);
});

test("Pi admission alone does not acknowledge a wake before consumption", async t => {
  const state = await fixture(t);
  assert.deepEqual(await deliverJobEvent({ ...state, sendWake: async () => ({ accepted: true, pending: true }) }), []);
  assert.deepEqual(state.receipts, [{ channel: "wake", delivered: false }]);
  assert.deepEqual(await deliverJobEvent({ ...state, sendWake: async () => ({ accepted: true, consumed: true }) }), []);
  assert.equal(state.completed.has("wake"), true);
});

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
const settled = () => new Promise(resolve => setImmediate(resolve));

test("observation limits are global and per platform, with interleaved workspaces", async () => {
  const controller = new AbortController();
  const started = [];
  const pending = new Map();
  const scheduler = createObservationScheduler({ signal: controller.signal, intervalMs: Infinity, concurrency: 2,
    observe(item) {
      started.push(item.monitor_id);
      const operation = deferred();
      pending.set(item.monitor_id, operation);
      return operation.promise;
    },
    onResult() {},
  });
  scheduler.update([
    { workspace: "/a", monitor_id: "a1", platform: "Com30/qrun" },
    { workspace: "/a", monitor_id: "a2", platform: "Com30/slurm" },
    { workspace: "/b", monitor_id: "b1", platform: "FEDCluster/tri" },
    { workspace: "/b", monitor_id: "b2", platform: "Other/qrun" },
  ]);
  await settled();
  assert.deepEqual(started, ["a1", "b1"]);
  pending.get("b1").resolve({});
  await settled();
  // a2 shares the still occupied Com30 slot despite its different scheduler.
  assert.deepEqual(started, ["a1", "b1", "b2"]);
  pending.get("a1").resolve({});
  await settled();
  assert.deepEqual(started, ["a1", "b1", "b2", "a2"]);
  scheduler.stop();
  for (const operation of pending.values()) operation.resolve({});
  await scheduler.drain();
});

test("a slow Job does not delay later observations or overlap its own refresh", async () => {
  const slow = deferred();
  const controller = new AbortController();
  let clock = 1000;
  const started = [];
  const items = [
    { workspace: "/one", monitor_id: "slow", platform: "Com30/qrun" },
    { workspace: "/one", monitor_id: "fast", platform: "FEDCluster/tri" },
  ];
  const scheduler = createObservationScheduler({ signal: controller.signal, intervalMs: 100, now: () => clock,
    observe(item) { started.push(item.monitor_id); return item.monitor_id === "slow" ? slow.promise : Promise.resolve({}); },
    onResult() {},
  });
  scheduler.update(items);
  await settled();
  clock = 1200;
  scheduler.update(items);
  await settled();
  assert.deepEqual(started, ["slow", "fast", "fast"]);
  scheduler.stop();
  let drained = false;
  const draining = scheduler.drain().then(() => { drained = true; });
  await settled();
  assert.equal(drained, false);
  slow.resolve({});
  await draining;
});

test("a newly discovered workspace joins an existing platform backlog without resetting its rotation", async () => {
  const controller = new AbortController();
  const started = [];
  const pending = new Map();
  const existing = Array.from({ length: 4 }, (_, index) => ({
    workspace: "/existing", monitor_id: `a${index + 1}`, platform: "Com30/qrun",
  }));
  const scheduler = createObservationScheduler({ signal: controller.signal, intervalMs: Infinity,
    observe(item) {
      started.push(item.monitor_id);
      const operation = deferred();
      pending.set(item.monitor_id, operation);
      return operation.promise;
    },
    onResult() {},
  });
  try {
    scheduler.update(existing);
    await settled();
    assert.deepEqual(started, ["a1"]);
    pending.get("a1").resolve({});
    await settled();
    assert.deepEqual(started, ["a1", "a2"]);

    const updated = [...existing, { workspace: "/new", monitor_id: "b1", platform: "Com30/slurm" }];
    scheduler.update(updated);
    pending.get("a2").resolve({});
    await settled();
    assert.deepEqual(started, ["a1", "a2", "a3"]);
    // Repeated inventory refresh must retain both workspaces' current place.
    scheduler.update(updated);
    pending.get("a3").resolve({});
    await settled();
    assert.deepEqual(started, ["a1", "a2", "a3", "b1"]);
    pending.get("b1").resolve({});
    await settled();
    assert.deepEqual(started, ["a1", "a2", "a3", "b1", "a4"]);
  } finally {
    scheduler.stop();
    for (const operation of pending.values()) operation.resolve({});
    await scheduler.drain();
  }
});

test("delivery takes only the first immutable batch of each session", () => {
  const rows = [
    { session_id: "a", request_id: "a-first", event_id: "1" },
    { session_id: "a", request_id: "a-first", event_id: "2" },
    { session_id: "a", request_id: "a-next", event_id: "3" },
    { session_id: "b", request_id: "b-first", event_id: "4" },
  ];
  assert.deepEqual(firstSessionBatches(rows), [[rows[0], rows[1]], [rows[3]]]);
});

test("slow observations and a pending session do not block another session's delivery", async t => {
  const state = await fixture(t);
  const slow = deferred();
  t.after(() => slow.resolve({ monitors: [{ monitor_id: "slow", error: "remote timed out" }] }));
  const delivered = deferred();
  const pendingNotified = deferred();
  const controller = new AbortController();
  const wakes = [];
  const claims = [];
  const completed = [];
  const snapshots = [];
  const deliveries = [
    { event_id: "1", session_id: "pending-session", request_id: "first" },
    { event_id: "2", session_id: "pending-session", request_id: "later" },
    { event_id: "3", session_id: "ready-session", request_id: "ready" },
  ];
  const running = runJobWorkerLoops({ intervalMs: 1000, once: true }, controller.signal, {
    listWorkspaces: async () => [{ source_root: state.workspace }],
    async runJson(command, _workspace, args) {
      if (command === "observations") return { observations: [
        { monitor_id: "slow", platform: "Com30/qrun" },
        { monitor_id: "fast", platform: "FEDCluster/tri" },
      ] };
      if (command === "tick") {
        assert.deepEqual(args.slice(2), ["--timeout-seconds", "30"]);
        return args[1] === "slow" ? slow.promise : { monitors: [{ monitor_id: "fast" }] };
      }
      if (command === "pending") return { deliveries };
      if (command === "health") return {};
      const requestId = args[args.indexOf("--request-id") + 1];
      const delivery = deliveries.find(row => row.request_id === requestId);
      if (command === "claim") {
        claims.push(requestId);
        return { ...delivery, claimed: true, claim_token: "token", batch_event_ids: [delivery.event_id],
          events: [{ ...state.event, event_id: delivery.event_id }] };
      }
      assert.equal(command, "complete");
      completed.push({ requestId, delivered: args.includes("--delivered") });
      if (requestId === "ready") delivered.resolve();
      return {};
    },
    async sendWake(params) {
      wakes.push(params.request_id);
      if (params.session_id === "pending-session") pendingNotified.resolve();
      return params.session_id === "pending-session" ? { accepted: true, pending: true } : { accepted: true, consumed: true };
    },
    async publishHealth(value) { snapshots.push(value); },
  });
  await Promise.all([delivered.promise, pendingNotified.promise]);
  assert.deepEqual(new Set(claims), new Set(["first", "ready"]));
  assert.deepEqual(new Set(wakes), new Set(["first", "ready"]));
  assert.ok(completed.some(row => row.requestId === "ready" && row.delivered));
  slow.resolve({ monitors: [{ monitor_id: "slow", error: "remote timed out" }] });
  await running;
  const health = snapshots.at(-1);
  assert.match(health.last_observation_error, /remote timed out/);
  assert.equal(health.last_delivery_error, null);
  assert.ok(health.last_successful_delivery);
  assert.ok(health.last_successful_observation);
  assert.equal(health.last_successful_poll, null);
});

test("a complete event batch uses one claim and one completion", async t => {
  const state = await fixture(t);
  const events = Array.from({ length: JOB_EVENT_IDS_LIMIT }, (_, index) => ({ ...state.event, event_id: String(index + 1) }));
  const commands = [];
  let deliveredIds;
  const errors = await deliverJobEvent({ workspace: state.workspace, delivery: state.delivery,
    async runJson(command) {
      commands.push(command);
      if (command === "claim") return { claimed: true, claim_token: "all", request_id: state.delivery.request_id,
        session_id: state.delivery.session_id, batch_event_ids: events.map(row => row.event_id), events };
      assert.equal(command, "complete");
      return {};
    },
    async sendWake(params) { deliveredIds = params.event_ids; return { accepted: true, consumed: true }; },
  });
  assert.deepEqual(errors, []);
  assert.deepEqual(commands, ["claim", "complete"]);
  assert.equal(deliveredIds.length, JOB_EVENT_IDS_LIMIT);
});

test("once delivers events created after its first pending scan", async t => {
  const state = await fixture(t);
  const firstPending = deferred();
  let observed = false;
  let delivered = false;
  const wakes = [];
  await runJobWorkerLoops({ intervalMs: 1000, once: true }, new AbortController().signal, {
    listWorkspaces: async () => [{ source_root: state.workspace }],
    async runJson(command, workspace, args) {
      if (command === "observations") return { observations: [{ monitor_id: "one", platform: "Com30/qrun" }] };
      if (command === "tick") {
        await firstPending.promise;
        observed = true;
        return { monitors: [{ monitor_id: "one" }] };
      }
      if (command === "pending") {
        firstPending.resolve();
        return { deliveries: observed && !delivered ? [state.delivery] : [] };
      }
      if (command === "health") return {};
      const result = await state.runJson(command, workspace, args);
      if (command === "complete" && args.includes("--delivered")) delivered = true;
      return result;
    },
    async sendWake(params) { wakes.push(params); return { accepted: true, consumed: true }; },
    async publishHealth() {},
  });
  assert.equal(observed, true);
  assert.equal(delivered, true);
  assert.equal(wakes.length, 1);
});
