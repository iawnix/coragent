export function workingLabel(view) {
  const live = view.docs?.["pi.live"] || {};
  if (live.generation?.retry) return `Retrying model request (attempt ${(live.generation.attempt ?? 0) + 1})…`;
  if (live.generation?.deferred) return "Waiting for model response…";
  if (live.compactions?.length) return "Compacting context…";
  const tool = live.tools?.find(item => item.status === "running");
  if (tool) return `Running ${tool.name}…`;
  return live.run ? "Working…" : "";
}

/** One fixed status row; its clock is independent of model output. */
export function createWorkingStatus({ Loader, Text, theme, requestRender, fallback,
  animated = process.env.TERM !== "dumb" && process.env.CORAGENT_TUI_ANIMATION !== "0" }) {
  let label = "", active = false, loader;
  const text = new Text("", 1, 0);
  function sync() {
    if (!active || !label || !animated) { loader?.stop(); loader = undefined; return; }
    if (!loader) loader = new Loader({ requestRender }, value => theme.fg("accent", value), value => theme.fg("muted", value), label);
    else loader.setMessage(label);
  }
  return {
    update(view) {
      const next = workingLabel(view);
      if (next === label) return;
      label = next; text.setText(theme.fg("muted", label)); sync(); requestRender();
    },
    setActive(value) { if (active !== value) { active = value; sync(); } },
    invalidate() { text.invalidate(); loader?.invalidate(); fallback.invalidate?.(); },
    render(width) {
      if (!label) return fallback.render(width);
      // Loader includes a leading spacer; status always occupies one row.
      return [loader ? loader.render(width)[1] ?? "" : text.render(width)[0] ?? ""];
    },
    dispose() { active = false; loader?.stop(); loader = undefined; },
  };
}
