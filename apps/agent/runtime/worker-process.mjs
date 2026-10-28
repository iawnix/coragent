import { fork } from "node:child_process";
import { join } from "node:path";
import { piModulePath } from "./source.mjs";

/** One supervised process and one in-flight startup per durable session. */
export function startSessionWorker({ sourceRoot, packageRoot, metadata, producerToken, model, onView, onExit }) {
  const pending = new Map();
  let nextId = 0, ready = false, stopped = false, exited = false, closePromise;
  const child = fork(join(packageRoot, "apps/agent/runtime/worker.mjs"), [], {
    cwd: metadata.cwd,
    execArgv: ["--import", piModulePath("resolver", sourceRoot)],
    env: { ...process.env, CORAGENT_PI_RUNTIME_ROOT: sourceRoot, CORAGENT_PACKAGE_ROOT: packageRoot,
      CORAGENT_INPUT_PRODUCER_TOKEN: producerToken },
    stdio: ["ignore", "ignore", "inherit", "ipc"],
  });
  // `close` also fires when spawning fails and there is no `exit` event.
  const ended = new Promise(resolve => child.once("close", resolve));
  function fail(cause) {
    for (const request of pending.values()) { clearTimeout(request.timer); request.reject(cause); }
    pending.clear();
  }
  function request(method, params, timeoutMs = 60_000) {
    if (exited || !child.connected) return Promise.reject(Object.assign(new Error("Session worker is unavailable"), { code: "worker_unavailable" }));
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(Object.assign(new Error(`Worker request timed out: ${method}`), { code: "request_timeout" }));
      }, timeoutMs);
      timer.unref();
      pending.set(id, { resolve, reject, timer });
      child.send({ id, method, params }, error => {
        if (error && pending.delete(id)) { clearTimeout(timer); reject(error); }
      });
    });
  }
  child.on("message", message => {
    if (message.type === "view") { onView(message.value); return; }
    const waiting = pending.get(message.id);
    if (!waiting) return;
    clearTimeout(waiting.timer); pending.delete(message.id);
    if (message.error) waiting.reject(Object.assign(new Error(message.error.message), { code: message.error.code }));
    else waiting.resolve(message.result);
  });
  child.on("error", cause => { fail(cause); });
  child.once("exit", (code, signal) => {
    exited = true;
    fail(Object.assign(new Error(`Session worker exited: ${signal || code}`), { code: "worker_unavailable" }));
    if (ready && !stopped) onExit?.({ code, signal });
  });
  async function close() {
    if (closePromise) return closePromise;
    stopped = true;
    closePromise = (async () => {
      if (exited) return;
      try { await request("close", {}, 5000); } catch { /* Force termination below. */ }
      if (!exited) child.kill("SIGTERM");
      const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
      try { await ended; } finally { clearTimeout(timer); }
    })();
    return closePromise;
  }
  const startup = request("open", { metadata, model }, 60_000).then(value => { ready = true; return value; });
  return { pid: child.pid, request, close, startup, isClosed: () => exited || stopped };
}
