import { loadPi } from "./source.mjs";

/**
 * Adapt CoRAgent's shared credentials document to Pi's public CredentialStore.
 * The adapter lives in product code so Pi's AuthStorage does not need to know
 * about CoRAgent's `models`/`secrets` document or its installation layout.
 */
export async function createCoRAgentCredentialStore({ sourceRoot, path = process.env.CORAGENT_CREDENTIALS_FILE } = {}) {
  const { AuthStorage, FileAuthStorageBackend } = await loadPi("authStorage", sourceRoot);
  if (!path) return AuthStorage.create();
  const file = new FileAuthStorageBackend(path);
  const unpack = current => {
    const document = JSON.parse(current ?? '{"models":{},"secrets":{}}');
    if (!document || typeof document !== "object" || Array.isArray(document)
      || !document.models || typeof document.models !== "object" || Array.isArray(document.models)) {
      throw new Error("Invalid CoRAgent credentials document");
    }
    return document;
  };
  const wrap = (current, result) => ({
    result: result.result,
    next: result.next === undefined ? undefined
      : JSON.stringify({ ...unpack(current), models: JSON.parse(result.next) }, null, 2) + "\n",
  });
  return AuthStorage.fromStorage({
    withLock: fn => file.withLock(current => wrap(current, fn(JSON.stringify(unpack(current).models)))),
    withLockAsync: (fn, options) => file.withLockAsync(async current => wrap(current, await fn(JSON.stringify(unpack(current).models))), options),
  });
}
