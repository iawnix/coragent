import { isDeepStrictEqual } from "node:util";

/** A presentation-only stream. A new connection always starts with a full view. */
export function createViewStream() {
  let previous, sequence = 0;
  return {
    next(view) {
      if (!previous) {
        previous = view;
        return { sequence: ++sequence, view };
      }
      const before = previous.entries, after = view.entries;
      let start = 0, end = 0;
      while (start < Math.min(before.length, after.length) && isDeepStrictEqual(before[start], after[start])) start++;
      while (end < Math.min(before.length, after.length) - start
        && isDeepStrictEqual(before[before.length - end - 1], after[after.length - end - 1])) end++;
      const entries = start === before.length && start === after.length ? undefined
        : { start, deleteCount: before.length - start - end, items: after.slice(start, after.length - end) };
      const docs = Object.fromEntries(Object.entries(view.docs).filter(([key, value]) => !isDeepStrictEqual(previous.docs[key], value)));
      const removed = Object.keys(previous.docs).filter(key => !Object.hasOwn(view.docs, key));
      const failure = view.failure ?? null;
      if (!entries && !Object.keys(docs).length && !removed.length && isDeepStrictEqual(previous.failure ?? null, failure)
        && isDeepStrictEqual(previous.conversation, view.conversation)) return null;
      previous = view;
      return { base: sequence, sequence: ++sequence, ...(entries ? { entries } : {}), docs, removed, failure, conversation: view.conversation };
    },
  };
}

/** Retain unchanged entry identities so renderers can reuse history across frames. */
export function createViewReplica() {
  let view, sequence = 0;
  return {
    apply(frame) {
      if (!Number.isSafeInteger(frame?.sequence) || frame.sequence <= 0) throw new Error("Invalid view sequence");
      if (frame.sequence <= sequence) return null;
      if (frame.view) {
        if (!Array.isArray(frame.view.entries) || !frame.view.docs) throw new Error("Invalid view snapshot");
        view = frame.view;
      } else {
        if (!view || frame.base !== sequence || frame.sequence !== sequence + 1) throw new Error("Session view needs resynchronization");
        let entries = view.entries;
        if (frame.entries) {
          const { start, deleteCount, items } = frame.entries;
          if (!Number.isSafeInteger(start) || start < 0 || start > entries.length
            || !Number.isSafeInteger(deleteCount) || deleteCount < 0 || deleteCount > entries.length - start
            || !Array.isArray(items)) throw new Error("Invalid view entries");
          entries = [...entries.slice(0, start), ...items, ...entries.slice(start + deleteCount)];
        }
        const docs = { ...view.docs, ...frame.docs };
        // Live documents bundle generation, tools and compaction. A token update
        // must not invalidate otherwise unchanged tool cards or status panels.
        for (const [key, value] of Object.entries(frame.docs || {})) {
          if (!value || typeof value !== "object" || Array.isArray(value)) continue;
          docs[key] = Object.fromEntries(Object.entries(value).map(([field, item]) =>
            [field, isDeepStrictEqual(view.docs[key]?.[field], item) ? view.docs[key]?.[field] : item]));
        }
        for (const key of frame.removed || []) delete docs[key];
        view = { ...view, entries, docs, failure: frame.failure, conversation: frame.conversation };
      }
      sequence = frame.sequence;
      return view;
    },
  };
}
