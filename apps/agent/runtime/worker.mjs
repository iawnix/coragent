import { createRequire } from "node:module";
import { join } from "node:path";
import { backupBeforeMigration } from "./storage.mjs";
import { compactionOutcome } from "./compaction.mjs";
import { inspectRuntime, retryRuntimeTask } from "./inspection.mjs";
import { getSupportedThinkingLevels } from "@earendil-works/pi-ai";
import { createViewStream } from "../transport/view-stream.mjs";

if (!process.send) throw new Error("Session worker requires a supervised IPC channel");
process.umask(0o077);
let runtime, context, watch, release, startup, closing, viewTimer, latestView;
const viewStream = createViewStream();
const send = value => new Promise((resolve, reject) => {
  if (!process.connected) { resolve(); return; }
  process.send(value, error => error ? reject(error) : resolve());
});


async function open({ metadata, model }) {
  if (startup) throw new Error("Worker has already been initialized");
  startup = (async () => {
    const require = createRequire(join(process.env.CORAGENT_PI_RUNTIME_ROOT, "package.json"));
    const lockfile = require("proper-lockfile");
    release = await lockfile.lock(metadata.path, { realpath: true, stale: 30_000,
      retries: { retries: 35, minTimeout: 1000, maxTimeout: 1000 },
      onCompromised: error => { console.error(error.message); process.exit(1); } });
    const databasePath = join(metadata.path, "session.sqlite");
    await backupBeforeMigration(databasePath);
    const [{ createCoRAgentHarness }, { BACKGROUND_CONTEXT }] = await Promise.all([
      import("./setup.mjs"), import("@earendil-works/chord/context"),
    ]);
    context = BACKGROUND_CONTEXT;
    runtime = await createCoRAgentHarness(databasePath, { metadata, provider: model?.provider, model: model?.id });
    watch = await runtime.conversation.watch(context);
    latestView = watch.value;
    watch.start(async value => {
      latestView = value;
      if (!viewTimer && !closing) viewTimer = setTimeout(() => {
        viewTimer = undefined;
        const frame = viewStream.next(latestView);
        if (frame) void send({ type: "view", frame }).catch(() => close());
      }, 16);
    });
    void watch.closed.then(end => { if (!closing && end.reason !== "stopped") shutdown(); });
    runtime.harness.resume();
    return latestView;
  })();
  return startup;
}

async function close() {
  if (closing) return closing;
  closing = (async () => {
    await startup?.catch(() => {});
    clearTimeout(viewTimer);
    await watch?.stop();
    try { await runtime?.cleanup(context); }
    finally {
      try { await runtime?.harness.close(context); }
      finally { await release?.(); }
    }
  })();
  return closing;
}

async function handle(method, params) {
  if (method === "open") return open(params);
  if (method === "close") { await close(); return { closed: true }; }
  if (closing) throw new Error("Worker is closing");
  await startup;
  if (!runtime) throw new Error("Worker is not initialized");
  if (method === "runtime/status") return inspectRuntime(runtime.harness, context);
  if (method === "runtime/retry") return retryRuntimeTask(runtime.harness, params.task_id, context);
  if (method === "snapshot") {
    // A watch may lag the transaction that just acknowledged an input.
    const state = await runtime.conversation.viewState(context);
    try { return state.value; } finally { await state.dispose(context); }
  }
  if (method === "compaction/status") return compactionOutcome(runtime.harness, runtime.conversation, params.task_id, context);
  if (method === "service") {
    const service = runtime.services[params.service];
    if (!service || !Object.hasOwn(service, params.method) || typeof service[params.method] !== "function") throw new Error("Unknown worker service method");
    return params.args === undefined ? service[params.method](context) : service[params.method](params.args, context);
  }
  if (method === "models/list") {
    const agent = await runtime.conversation.agent(context);
    const model = agent.model && runtime.modelRuntime.getModel(agent.model.provider, agent.model.modelId);
    return { models: await runtime.modelRuntime.getAvailable(), selected: agent.model ?? null,
      thinking_level: agent.thinkingLevel || "off", thinking_levels: model ? getSupportedThinkingLevels(model) : ["off"] };
  }
  if (method === "model/select") {
    const model = runtime.modelRuntime.getModel(params.provider, params.id);
    if (!model) throw Object.assign(new Error("Model is not available"), { code: "model_not_found" });
    await runtime.conversation.configure({ model: { provider: model.provider, modelId: model.id } }, context);
    return { accepted: true };
  }
  if (method === "compact") {
    const id = await runtime.conversation.compact(params.instructions, context);
    return { task_id: String(id) };
  }
  if (method === "configure") {
    if (!["off", "minimal", "low", "medium", "high", "xhigh"].includes(params.thinkingLevel)) throw new Error("Unknown thinking level");
    const agent = await runtime.conversation.agent(context);
    const model = agent.model && runtime.modelRuntime.getModel(agent.model.provider, agent.model.modelId);
    if (!model || !getSupportedThinkingLevels(model).includes(params.thinkingLevel)) throw new Error("Thinking level is not supported by the selected model");
    await runtime.conversation.configure({ thinkingLevel: params.thinkingLevel }, context);
    return { accepted: true };
  }
  if (method === "reload") {
    const result = await runtime.modelRuntime.refresh({ allowNetwork: false });
    if (result.errors.size) throw new Error([...result.errors.values()].map(error => error.message).join("; "));
    return { accepted: true };
  }
  if (method === "abort") { await runtime.conversation.abort(context); return { accepted: true }; }
  throw new Error(`Unsupported worker method: ${method}`);
}

process.on("message", message => {
  if (!message || !Number.isSafeInteger(message.id) || typeof message.method !== "string") return;
  void (async () => {
    try { await send({ id: message.id, result: await handle(message.method, message.params ?? {}) }); }
    catch (error) { await send({ id: message.id, error: { code: error.code || "worker_error", message: error.message } }); }
    if (message.method === "close") process.disconnect();
  })().catch(() => shutdown());
});
function shutdown() {
  void close().then(() => process.exit(0), error => { console.error(error); process.exit(1); });
}
process.on("disconnect", shutdown);
for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"]) process.on(signal, shutdown);
