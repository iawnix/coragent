import { chmod, lstat, mkdir, open, rename, unlink } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import { gzip } from "node:zlib";

const compress = promisify(gzip);
const HEADER_ALLOWLIST = ["content-type", "session_id", "x-session-id", "x-session-affinity",
  "x-client-request-id", "conversation_id", "openai-beta"];

/** Opt-in local capture. Bodies are intentionally complete and may contain private user content.
 * Authentication headers, cookies, URL credentials and query strings are never persisted.
 */
export function requestCaptureWriter(directory, { sessionId, workspaceId } = {}) {
  return async function capture({ url, init, record }) {
    if (typeof init?.body !== "string") return { status: "unsupported_body" };
    let temporary;
    try {
      await mkdir(directory, { recursive: true, mode: 0o700 });
      const info = await lstat(directory);
      if (!info.isDirectory() || info.isSymbolicLink()) return { status: "error", code: "UNSAFE_DIRECTORY" };
      await chmod(directory, 0o700);
      const endpoint = new URL(url);
      const headers = new Headers(init.headers);
      const savedHeaders = Object.fromEntries(HEADER_ALLOWLIST
        .filter(name => headers.has(name)).map(name => [name, headers.get(name)]));
      const file = `${record.started_at_ms}-${record.request_id}-${record.attempt}.request.json.gz`;
      const archive = {
        ...record, schema_version: "coragent-request-capture/1", session_id: sessionId, workspace_id: workspaceId,
        endpoint: endpoint.origin + endpoint.pathname, method: init.method ?? "POST",
        headers: savedHeaders, body: init.body,
      };
      const bytes = await compress(JSON.stringify(archive));
      const pending = join(directory, `${file}.tmp`);
      const handle = await open(pending, "wx", 0o600);
      temporary = pending;
      try { await handle.writeFile(bytes); } finally { await handle.close(); }
      await rename(temporary, join(directory, file));
      temporary = undefined;
      return { status: "saved", file, body_bytes: Buffer.byteLength(init.body), archive_bytes: bytes.length };
    } catch (error) {
      // Do not leak filesystem paths, request content or credentials through error messages.
      return { status: "error", code: /^[A-Z_]+$/.test(error?.code ?? "") ? error.code : "CAPTURE_FAILED" };
    } finally {
      if (temporary) await unlink(temporary).catch(() => {});
    }
  };
}
