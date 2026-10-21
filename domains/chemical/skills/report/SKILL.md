---
name: report
description: Assemble traceable research reports from structures, calculations, validation evidence, energy data, figures, and conclusions.
---

# Research reports

[Chinese version](SKILL.zh-CN.md)

## Script routing

Use the registered executor ID and the [script routing map](../../../../docs/skill-script-routing.md#report) to choose the entrypoint, CLI, inputs, and primary outputs. The map is authoritative for routing; implementation helpers under `scripts/` are not standalone commands. Do not inspect source code to discover invocation details; read the linked operation contract and use executor `--help` only for unspecified options.

**Entrypoints:** `chemical.render@1` → `skills/report/scripts/render.py`; `chemical.trajectory@1` → `skills/report/scripts/research_job.py`; `chemical.research-report@1` → `skills/report/scripts/research_job.py`.

Use this Skill when a study needs a readable evidence package. A report should answer the research question, show the methods and source records, distinguish observations from interpretation, and make missing or conflicting evidence visible.

## Report workflow

1. Collect result JSON, CSV, geometries, logs, validation records, and source digests. Build a small dataset with one row per structure, candidate, energy state, or path frame.
2. Use `scripts/build.py` for a first evidence table:

```bash
"$CORAGENT_PYTHON" <installed-report-skill>/scripts/build.py --result local=<workspace>/path/to/result.json --output-dir <workspace>/reports/comparison-v1
```

3. Render supplied geometries with `chemical.render@1` (`--style`, `--size`, `--charge`, `--multiplicity`) and include captions identifying the Artifact and state.
4. Plot energy profiles, scan slices, ensemble populations, and trajectories from collected data. Keep units, standard state, temperature, gaps, and excluded rows in the figure or caption.
5. Write conclusions beside the evidence that supports them. For TS studies, show candidate identity, imaginary mode, IRC endpoints, and validation status. For energy studies, show E/ZPE/H/G labels and method/condition metadata. For kinetics, show TST assumptions, precursor scope, concentrations, conservation diagnostics, and terminal status.
6. Register the report, figures, data, and scripts as materials and cite them in the research conclusion. Use `chemical.research-report@1` for an illustrated Markdown package and `chemical.trajectory@1` for fixed-camera GIF/XYZ/CSV path products.

## Delivery and review

The report may be Markdown with an image directory, HTML, PDF, or another requested format. Open the final document and inspect links, axes, captions, units, tables, and provenance. Use the report email adapter only after the user authorizes sending; prepare/check/status operations are in [report email delivery](references/report_email_delivery.md).

For energy datasets, read [energy contracts](../energetics/references/energy_execution.md). For trajectories and report packages, read [research tools](references/research_tools.md) and [illustrated reports](references/illustrated_report.md).
