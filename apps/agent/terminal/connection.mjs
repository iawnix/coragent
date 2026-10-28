/** Reattach through the Host after a transport failure; snapshots recover missed frames. */
export function subscribeSession({ connect, workspaceId, sessionId, onView, onError, retryMs = 1000 }) {
  let stopped = false, peer, retryTimer, refreshTimer, reading = false, dirty = false;
  const scope = { workspace_id: workspaceId, session_id: sessionId };
  async function refresh() {
    if (stopped || !peer) return;
    if (reading) { dirty = true; return; }
    reading = true; dirty = false;
    const connection = peer;
    try {
      const view = await connection.request("session/query", { ...scope, query: "view" });
      if (!stopped && peer === connection) onView(view);
    } catch (error) { if (!stopped && peer === connection) onError(error); }
    finally {
      reading = false;
      if (dirty && !stopped) schedule();
    }
  }
  function schedule() {
    dirty = true;
    if (!refreshTimer) refreshTimer = setTimeout(() => { refreshTimer = undefined; void refresh(); }, 20);
  }
  function retry(error) {
    if (stopped) return;
    onError(error); clearTimeout(retryTimer);
    retryTimer = setTimeout(open, retryMs);
  }
  async function open() {
    let connection;
    try {
      connection = await connect();
      if (stopped) { connection.close(); return; }
      peer = connection;
      connection.on("notification", event => {
        if (event.method === "session/event" && event.params.workspace_id === workspaceId && event.params.session_id === sessionId) schedule();
      });
      connection.on("close", error => { if (peer === connection) { peer = undefined; retry(error); } });
      await connection.request("session/attach", { ...scope, presentation: "terminal" });
      await refresh();
    } catch (error) {
      if (peer === connection) peer = undefined;
      connection?.close(); retry(error);
    }
  }
  void open();
  return () => {
    stopped = true; clearTimeout(retryTimer); clearTimeout(refreshTimer);
    const previous = peer; peer = undefined; previous?.close();
  };
}
