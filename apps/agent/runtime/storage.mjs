import { chmod, lstat, rename, rm } from "node:fs/promises";
import { DatabaseSync, backup } from "node:sqlite";

/** Online SQLite backup includes WAL pages; a plain file copy does not. */
export async function backupBeforeMigration(path) {
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error("Session database must be a regular file");
  } catch (error) { if (error.code === "ENOENT") return; throw error; }
  const db = new DatabaseSync(path, { readOnly: true });
  try {
    const table = db.prepare("SELECT name FROM sqlite_master WHERE name = 'durable_schema'").get();
    if (!table || Number(db.prepare("SELECT MAX(version) AS version FROM durable_schema").get().version) >= 2) return;
    const target = `${path}.pre-pi-1.4`;
    try {
      const info = await lstat(target);
      if (!info.isFile() || info.isSymbolicLink()) throw new Error("Session backup must be a regular file");
      return;
    } catch (error) { if (error.code !== "ENOENT") throw error; }
    const temporary = `${target}.tmp`;
    await rm(temporary, { force: true });
    try { await backup(db, temporary); await chmod(temporary, 0o600); await rename(temporary, target); }
    finally { await rm(temporary, { force: true }); }
  } finally { db.close(); }
}
