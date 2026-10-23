import { lstat, readFile, readdir, realpath } from "node:fs/promises";
import { join } from "node:path";
import { validate_workspace_manifest } from "../workspace.mjs";
import bindingSchema from "../../../../contracts/monitor/jobs/binding.schema.json" with { type: "json" };
import eventSchema from "../../../../contracts/monitor/jobs/event.schema.json" with { type: "json" };
import { Value } from "../../runtime/typebox.mjs";
const MONITOR_ID = /^monitor_[1-9][0-9]*$/u;
const MONITOR_EVENT_ID = /^event_[1-9][0-9]*$/u;

export function createJobEvents({ listWorkspaces, clients, epoch }) {
  const monitorFiles = new Map();
  let monitorSequence = 0, polling = false, closed = false;
  async function scanMonitorFiles({ notify = true } = {}) {
    if (polling || closed) return;
    polling = true;
    try {
      for (const project of await listWorkspaces()) {
        const identity = await monitorWorkspaceIdentity(project);
        if (!identity) continue;
        const root = join(project.root, "operations", "monitors");
        if (!await isPhysicalDirectory(root)) continue;
        let registrations;
        try { registrations = await readdir(root, { withFileTypes: true }); } catch { continue; }
        for (const registration of registrations) {
          if (!registration.isDirectory() || !MONITOR_ID.test(registration.name)) continue;
          const registrationRoot = join(root, registration.name);
          if (!await isPhysicalDirectory(registrationRoot)) continue;
          const registrationPath = join(registrationRoot, "binding.json");
          if (!await isPhysicalFile(registrationPath)) continue;
          let binding;
          try { binding = JSON.parse(await readFile(registrationPath, "utf8")); } catch { continue; }
          if (!validMonitorBinding(binding, registration.name, identity)) continue;
          const eventsRoot = join(registrationRoot, "events");
          if (!await isPhysicalDirectory(eventsRoot)) continue;
          let entries;
          try { entries = await readdir(eventsRoot, { withFileTypes: true }); } catch { continue; }
          for (const entry of entries) {
            if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
            const eventId = entry.name.slice(0, -5);
            if (!MONITOR_EVENT_ID.test(eventId)) continue;
            const path = join(eventsRoot, entry.name);
            const info = await physicalFileInfo(path);
            if (!info) continue;
            const bindingMarker = [identity.route, identity.canonical, binding.job_id,
              binding.job_digest, binding.node_id, binding.node_revision, binding.user_task_id, binding.session_id, binding.wake_policy, binding.notify_policy].map((value) => JSON.stringify(value)).join(":");
            const marker = `${info.dev}:${info.ino}:${info.size}:${info.mtimeMs}:${bindingMarker}`;
            if (monitorFiles.get(path) === marker) continue;
            let event;
            try { event = JSON.parse(await readFile(path, "utf8")); } catch { continue; }
            // A workspace can contain hand-written or stale monitor files.
            // Do not relay them to Phone clients unless the file, registration,
            // and workspace identity all agree.
            if (!validMonitorEvent(event, eventId, registration.name, identity, binding)) {
              continue;
            }
            monitorFiles.set(path, marker);
            if (!notify) continue;
            const params = { workspace_id: project.workspace_id, epoch, sequence: ++monitorSequence, event };
            for (const client of clients) if (client.monitorWorkspaces.has(project.workspace_id)) {
              try { client.peer.notify("monitor/event", params); } catch { client.peer.close(); }
            }
          }
        }
      }
    } finally { polling = false; }
  }

  async function pollMonitors() {
    return scanMonitorFiles();
  }
  return { scanMonitorFiles, pollMonitors, stop() { closed = true; } };
}

async function isPhysicalDirectory(path) {
  try {
    const info = await lstat(path);
    return info.isDirectory() && !info.isSymbolicLink() && await realpath(path) === path;
  } catch {
    return false;
  }
}

async function isPhysicalFile(path) {
  try {
    const info = await lstat(path);
    return info.isFile() && !info.isSymbolicLink() && await realpath(path) === path;
  } catch {
    return false;
  }
}

async function physicalFileInfo(path) {
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink() || await realpath(path) !== path) return null;
    return info;
  } catch {
    return null;
  }
}

async function monitorWorkspaceIdentity(project) {
  const manifestPath = join(project.root, "workspace_manifest.json");
  if (!await isPhysicalFile(manifestPath)) return null;
  try {
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    validate_workspace_manifest(manifest, project.root);
    if (manifest.state !== "ready") return null;
    const canonical = manifest.workspace_id;
    return { route: project.workspace_id, canonical };
  } catch {
    return null;
  }
}

function validMonitorBinding(binding, monitorId, identity) {
  return Value.Check(bindingSchema, binding)
    && binding.monitor_id === monitorId
    && binding.workspace_id === identity.canonical;
}

function validMonitorEvent(event, eventId, monitorId, identity, binding) {
  return Value.Check(eventSchema, event)
    && event.event_id === eventId
    && event.monitor_id === monitorId
    && event.workspace_id === identity.canonical
    && ["job_id", "job_digest", "node_id", "node_revision", "user_task_id", "session_id", "wake_policy", "notify_policy"]
      .every(key => event[key] === binding[key]);
}
