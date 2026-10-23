/** Interleave workspaces before applying the shared observation limits. */
export function interleaveWorkspaces(items) {
  const groups = new Map();
  for (const item of items) {
    if (!groups.has(item.workspace)) groups.set(item.workspace, []);
    groups.get(item.workspace).push(item);
  }
  const result = [];
  for (let index = 0; groups.size; index++) {
    for (const [workspace, rows] of groups) {
      result.push(rows[index]);
      if (index + 1 === rows.length) groups.delete(workspace);
    }
  }
  return result;
}

/** A slow target occupies its own slot, without holding up another poll cycle. */
export function createObservationScheduler({ observe, onResult, signal, intervalMs, concurrency = 4, now = Date.now }) {
  const entries = new Map();
  const running = new Map();
  const platforms = new Set();
  let queue = [];
  let stopped = false;
  const keyOf = (item) => JSON.stringify([item.workspace, item.monitor_id]);
  const platformOf = (item) => item.platform.split("/")[0];
  const pump = () => {
    while (!stopped && !signal.aborted && running.size < concurrency) {
      const index = queue.findIndex(key => {
        const entry = entries.get(key);
        return entry.due <= now() && !running.has(key) && !platforms.has(platformOf(entry.item));
      });
      if (index === -1) break;
      const [key] = queue.splice(index, 1);
      queue.push(key);
      const entry = entries.get(key);
      const platform = platformOf(entry.item);
      platforms.add(platform);
      const operation = Promise.resolve().then(() => observe(entry.item)).then(
        result => onResult(entry.item, result, null),
        error => onResult(entry.item, null, error),
      ).finally(() => {
        entry.due = now() + intervalMs;
        running.delete(key);
        platforms.delete(platform);
        pump();
      });
      running.set(key, operation);
    }
  };
  return {
    update(items) {
      const ordered = interleaveWorkspaces(items);
      const keys = new Set(ordered.map(keyOf));
      for (const key of entries.keys()) if (!keys.has(key)) entries.delete(key);
      queue = queue.filter(key => keys.has(key));
      for (const item of ordered) {
        const key = keyOf(item);
        if (entries.has(key)) entries.get(key).item = item;
        else { entries.set(key, { item, due: 0 }); queue.push(key); }
      }
      // Admit new workspaces into the current rotation while preserving each
      // workspace's remaining order, including Jobs already moved to its tail.
      queue = interleaveWorkspaces(queue.map(key => entries.get(key).item)).map(keyOf);
      pump();
    },
    async drain() { while (running.size) await Promise.allSettled([...running.values()]); },
    stop() { stopped = true; },
  };
}

export async function mapConcurrent(items, concurrency, operation) {
  let index = 0;
  const results = new Array(items.length);
  await Promise.all(Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    while (index < items.length) {
      const current = index++;
      results[current] = await operation(items[current]);
    }
  }));
  return results;
}

/** A pending first batch keeps later batches of that session out of admission. */
export function firstSessionBatches(deliveries) {
  const sessions = new Map();
  for (const delivery of deliveries) {
    if (!sessions.has(delivery.session_id)) sessions.set(delivery.session_id, []);
    const batch = sessions.get(delivery.session_id);
    if (!batch.length || batch[0].request_id === delivery.request_id) batch.push(delivery);
  }
  return [...sessions.values()];
}
