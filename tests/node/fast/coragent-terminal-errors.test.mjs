import assert from "node:assert/strict";
import test from "node:test";

import { formatError, formatTerminalFailure } from "../../../apps/agent/terminal/errors.mjs";

test("missing installation model configuration explains Pi's opaque startup failure", () => {
  const message = formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    fileExists: () => false,
  });

  assert.match(message, /^Internal server error\n/);
  assert.match(message, /Missing CoRAgent configuration/);
  assert.match(message, /\/home\/test\/\.config\/coragent\/config\.toml/);
  assert.match(message, /\/home\/test\/\.config\/coragent\/credentials\.json/);
  assert.match(message, /restart the CoRAgent Host/);
});

test("terminal failures include a diagnostic location when Pi configuration exists", () => {
  const message = formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    fileExists: () => true,
  });
  assert.match(message, /^Internal server error\nDiagnosis:/);
  assert.match(message, /worker-diagnostics\.log/);
  assert.match(formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    fileExists: (path) => path.endsWith("config.toml"),
  }), /Missing CoRAgent configuration: \/home\/test\/\.config\/coragent\/credentials\.json/);
  assert.equal(formatTerminalFailure(new Error("connection failed"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    fileExists: () => false,
  }), "connection failed");
});

test("worker diagnostics identify the Pi Durable details context mismatch", () => {
  const message = formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    diagnosticFile: "/home/test/.local/state/coragent/logs/worker-diagnostics.log",
    fileExists: () => true,
    readFile: () => "TypeError: Cannot read properties of undefined (reading 'abortSignal')\n",
  });

  assert.match(message, /incompatible with the pinned Pi Durable API/);
  assert.match(message, /details\(\) was called without its execution context/);
});

test("worker diagnostics identify stale durable session locks", () => {
  const message = formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    diagnosticFile: "/home/test/.local/state/coragent/logs/worker-diagnostics.log",
    fileExists: () => true,
    readFile: () => "Error: Unable to update lock within the stale threshold\n",
  });

  assert.match(message, /durable session lock is stale/);
  assert.match(message, /do not delete session databases/);
});

test("worker diagnostics are surfaced for opaque Pi startup failures", () => {
  const message = formatTerminalFailure(new Error("Internal server error"), {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    diagnosticFile: "/home/test/.local/state/coragent/logs/worker-diagnostics.log",
    fileExists: () => true,
    readFile: () => "Error: provider auth failed\n    at worker (worker.ts:42)\n",
  });

  assert.match(message, /Pi Worker diagnostics/);
  assert.match(message, /provider auth failed/);
  assert.doesNotMatch(message, /Missing CoRAgent configuration/);
});

test("nested service failures retain their actionable cause", () => {
  const failure = new AggregateError([
    new Error("Internal server error"),
    new Error("cleanup failed"),
  ], "Failed to rebind services", { cause: new Error("transport closed") });

  assert.equal(formatError(failure), "Failed to rebind services: Internal server error: cleanup failed: transport closed");
  const message = formatTerminalFailure(failure, {
    installRoot: "/home/test/coragent",
    configFile: "/home/test/.config/coragent/config.toml",
    credentialsFile: "/home/test/.config/coragent/credentials.json",
    fileExists: () => false,
  });
  assert.match(message, /^Failed to rebind services: Internal server error: cleanup failed: transport closed\n/);
  assert.match(message, /Possible cause: Missing CoRAgent configuration/);
});

test("stale Pi bindings explain Host restart recovery", () => {
  const message = formatError(new Error("Remote service pi.agent-controller binding is closed"));
  assert.match(message, /Host was restarted or upgraded/);
  assert.match(message, /relaunch coragent/);
});
