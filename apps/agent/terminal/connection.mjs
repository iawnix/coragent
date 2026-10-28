import { createViewReplica } from "../transport/view-stream.mjs";

/** Reconnect with a snapshot; steady-state streaming never queries the Worker. */
export function subscribeSession({ connect, workspaceId, sessionId, onView, onError, retryMs = 1000 }) {
  let stopped = false, peer, retryTimer;
  const scope = { workspace_id: workspaceId, session_id: sessionId };
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
      const replica = createViewReplica();
      let attached = false;
      const buffered = [];
      const receive = frame => { const view = replica.apply(frame); if (view) onView(view); };
      const fail = error => {
        if (peer !== connection) return;
        peer = undefined; connection.close(); retry(error);
      };
      connection.on("notification", event => {
        if (stopped || peer !== connection || event.method !== "session/view"
          || event.params.workspace_id !== workspaceId || event.params.session_id !== sessionId) return;
        try {
          if (attached) receive(event.params.frame);
          else if (buffered.length < 256) buffered.push(event.params.frame);
          else throw new Error("Session view attachment overflow");
        } catch (error) { fail(error); }
      });
      connection.on("close", error => fail(error));
      const { frame } = await connection.request("session/attach", { ...scope, presentation: "terminal", view_stream: true });
      if (stopped || peer !== connection) return;
      receive(frame);
      for (const pending of buffered) receive(pending);
      attached = true;
    } catch (error) {
      if (connection && peer !== connection) return;
      peer = undefined; connection?.close(); retry(error);
    }
  }
  void open();
  return () => {
    stopped = true; clearTimeout(retryTimer);
    const previous = peer; peer = undefined; previous?.close();
  };
}
