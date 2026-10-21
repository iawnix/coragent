// User language is interpreted by the agent; configuration matching has one
// authority in Jobs. Exact source excerpts make interpretation reviewable.
export async function resolveTaskSelection(kernel, params, sources, previous = null) {
  const intent = params.execution_intent;
  let selectedSources = sources;
  if (intent) {
    const source = sources.find(item => item.submission_id === intent.source_submission_id);
    if (!source || !intent.source_text?.trim() || !source.text.includes(intent.source_text))
      throw Object.assign(new Error("Execution intent must quote an actual cited user submission"), { code: "execution_source_invalid" });
    selectedSources = [{ ...source, text: intent.source_text }];
  }
  if (params.action === "correct_execution") {
    const anchor = intent?.scheduler || params.execution_target;
    if (!intent || !anchor || !intent.source_text.toLowerCase().includes(anchor.toLowerCase()))
      throw Object.assign(new Error("Correcting a target requires the original explicit target/scheduler instruction"), { code: "execution_correction_invalid" });
  }
  const selection = await kernel.execute_command("job.resolve_target", {
    ...(params.execution_target ? { target: params.execution_target } : {}),
    ...(intent?.scheduler ? { scheduler: intent.scheduler } : {}),
    ...(intent?.location ? { location: intent.location } : {}),
    source_text: selectedSources.map(item => item.text).join("\n"),
  });
  if (!selection?.target || !/^sha256:[a-f0-9]{64}$/.test(selection.route_digest || ""))
    throw Object.assign(new Error("Execution resolver did not return a pinned route"), { code: "execution_target_invalid" });
  return { ...selection, version: (previous?.version || 0) + 1,
    sources: selectedSources.map(({ submission_id, text }) => ({ submission_id, text })),
    resolved_at: new Date().toISOString() };
}
