import { randomUUID } from "node:crypto";
import { lstat, mkdir, readdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { isAbsolute, join } from "node:path";

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/u;
function identifier(value) {
  if (typeof value !== "string" || !ID.test(value)) throw Object.assign(new Error("Invalid session or workspace identifier"), { code: "invalid_identifier" });
  return value;
}
async function directory(path) {
  const info = await lstat(path);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error(`Session catalog requires a regular directory: ${path}`);
}

/** Keep the existing workspace/session/meta.json and session.sqlite layout. */
export function createSessionCatalog(root) {
  async function read(workspaceId, sessionId) {
    const workspace = join(root, identifier(workspaceId));
    const path = join(workspace, identifier(sessionId));
    try {
      await directory(root); await directory(workspace); await directory(path);
      const metaPath = join(path, "meta.json");
      const info = await lstat(metaPath);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error("Session metadata must be a regular file");
      const value = JSON.parse(await readFile(metaPath, "utf8"));
      if (!Number.isFinite(value.createdAt) || !isAbsolute(value.cwd || "")
        || (value.workspaceId !== undefined && value.workspaceId !== workspaceId)) throw new Error("Invalid session metadata");
      return { id: sessionId, sessionId, workspaceId, createdAt: value.createdAt, cwd: value.cwd, path };
    } catch (error) {
      if (error.code === "ENOENT") return undefined;
      throw error;
    }
  }
  return {
    read,
    async list() {
      await mkdir(root, { recursive: true, mode: 0o700 });
      await directory(root);
      const sessions = [];
      for (const workspace of await readdir(root, { withFileTypes: true })) {
        if (!workspace.isDirectory() || !ID.test(workspace.name)) continue;
        for (const entry of await readdir(join(root, workspace.name), { withFileTypes: true })) {
          if (!entry.isDirectory() || !ID.test(entry.name)) continue;
          const metadata = await read(workspace.name, entry.name);
          if (metadata) sessions.push(metadata);
        }
      }
      return sessions;
    },
    async create({ workspaceId, sessionId = randomUUID(), cwd }) {
      const workspace = join(root, identifier(workspaceId));
      const path = join(workspace, identifier(sessionId));
      await mkdir(root, { recursive: true, mode: 0o700 }); await directory(root);
      await mkdir(workspace, { recursive: true, mode: 0o700 }); await directory(workspace);
      try { await mkdir(path, { mode: 0o700 }); }
      catch (cause) {
        if (cause.code === "EEXIST") throw Object.assign(new Error("Session already exists"), { code: "session_exists" });
        throw cause;
      }
      const metadata = { createdAt: Date.now(), cwd, workspaceId };
      try {
        await writeFile(join(path, "meta.json.tmp"), JSON.stringify(metadata) + "\n", { mode: 0o600, flag: "wx" });
        await rename(join(path, "meta.json.tmp"), join(path, "meta.json"));
      } catch (cause) { await rm(path, { recursive: true, force: true }); throw cause; }
      return { ...metadata, id: sessionId, sessionId, path };
    },
    async remove(workspaceId, sessionId) {
      const metadata = await read(workspaceId, sessionId);
      if (metadata) await rm(metadata.path, { recursive: true, force: true });
    },
  };
}
