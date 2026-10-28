import { randomUUID } from "node:crypto";
import { lstatSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { formatTerminalFailure } from "../terminal/errors.mjs";
import { runTerminalSessions } from "../terminal/session.mjs";
import { subscribeMonitor } from "../terminal/status/monitor.mjs";
import { connectHost } from "../transport/host-client.mjs";
import { messageText } from "../terminal/chat.mjs";
import { runClientTui } from "../terminal/tui.mjs";

function parse(values) {
  const command = { prompt: undefined, json: false };
  const text = [];
  for (let index = 0; index < values.length; index++) {
    const value = values[index];
    if (["--connect", "--session-id", "--prompt"].includes(value)) {
      const argument = values[++index];
      if (!argument) throw new Error(`${value} requires a value`);
      command[{ "--connect": "connect", "--session-id": "sessionId", "--prompt": "prompt" }[value]] = argument;
    } else if (value === "--json") command.json = true;
    else if (value === "--print" || value === "-p") command.print = true;
    else if (value === "--") text.push(...values.slice(index + 1)), index = values.length;
    else if (value.startsWith("-")) throw new Error(`Unsupported terminal option: ${value}`);
    else text.push(value);
  }
  if (text.length) command.prompt = [command.prompt, ...text].filter(Boolean).join(" ");
  return command;
}

async function printClient(command, request, workspaceId) {
  const scope = { workspace_id: workspaceId, session_id: command.sessionId };
  if (command.prompt === undefined) {
    const result = await request("session/read", scope);
    console.log(command.json ? JSON.stringify(result) : `${workspaceId}\t${command.sessionId}\tattached`);
    return;
  }
  const id = randomUUID();
  let receipt;
  try { receipt = await request("input/send", { ...scope, request_id: id, client_message_id: id,
    text: command.prompt, source: "terminal", mode: "auto" }); }
  catch (error) {
    receipt = await request("input/status", { ...scope, client_message_id: id });
    if (!receipt.accepted) throw error;
  }
  if (!receipt.accepted) throw new Error(receipt.error?.message || "Input rejected");
  while (!["completed", "failed"].includes(receipt.state)) {
    await delay(100);
    receipt = await request("input/status", { ...scope, client_message_id: id });
  }
  const view = await request("session/query", { ...scope, query: "view" });
  const text = view.entries.filter(entry => entry.id > (receipt.submission?.entry || 0)
      && entry.id <= (receipt.submission?.answer ?? Number.POSITIVE_INFINITY))
    .flatMap(entry => entry.model || []).filter(message => message.role === "assistant")
    .map(message => messageText(message.content)).filter(Boolean).join("\n");
  console.log(command.json ? JSON.stringify({ ...receipt, text }) : text);
  if (receipt.state === "failed") throw new Error(receipt.error?.message || "Input failed");
}

try {
  const command = parse(process.argv.slice(2));
  const workspaceId = process.env.CORAGENT_WORKSPACE_ID;
  if (!command.sessionId || !workspaceId) throw new Error("Terminal requires a Host-selected workspace and session");
  const cwd = resolve(process.env.CORAGENT_SESSION_CWD || process.cwd());
  const info = lstatSync(cwd);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("Session cwd must be a regular directory");
  process.chdir(cwd);
  const socketPath = process.env.CORAGENT_HOST_SOCKET;
  if (!socketPath) throw new Error("Terminal requires CORAGENT_HOST_SOCKET");
  const connect = () => connectHost({ socketPath, expectedReleaseId: process.env.CORAGENT_HOST_RELEASE_ID || undefined });
  const request = async (method, params) => {
    const peer = await connect();
    try { return await peer.request(method, params); } finally { peer.close(); }
  };
  request.subscribeMonitor = (workspaceId, sessionId, onChange, onError) => subscribeMonitor({ connect, workspaceId, sessionId, onChange, onError });
  if (command.print || command.prompt !== undefined || !process.stdin.isTTY || !process.stdout.isTTY) await printClient(command, request, workspaceId);
  else await runTerminalSessions({ command, workspaceId, request,
    createFacet: async session => session,
    run: (_selected, options) => runClientTui({ session: options.facetLoader, request, connect,
      sourceRoot: process.env.CORAGENT_PI_RUNTIME_ROOT }),
  });
} catch (error) {
  console.error(`Error: ${formatTerminalFailure(error, { installRoot: process.env.CORAGENT_INSTALL_ROOT,
    diagnosticFile: process.env.CORAGENT_DIAGNOSTIC_FILE })}`);
  process.exitCode = 1;
}
