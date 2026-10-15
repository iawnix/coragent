---
name: report
description: Write illustrated research reports from evidence, with molecular structures, energy plots, data tables, methods, conclusions, and traceable sources.
---

# Research reports

Answer the user's research question with conclusions, evidence, methods, and
limitations, using the requested language and delivery format. A full report
should combine text and visuals: molecular images when structures are available,
energy plots for comparable energies, and tables of values and validation status.
Choose visuals from actual data; never invent structures, paths, energies, or
error bars to fill a layout.

Read [figures and report production](references/illustrated_report.md) to prepare
reproducible data tables, plotting scripts, images, and the final document.
Markdown with an image directory is a usable default; export HTML/PDF or other
requested formats with available tools. Embed figures with captions in the
report itself rather than providing only a list of image paths.

## Basic evidence table

For existing `science-result` files, invoke [scripts/build.py](scripts/build.py)
through native bash:

```bash
"$CORAGENT_PYTHON" <installed-report-skill>/scripts/build.py --result local=<workspace>/path/to/result.json --output-dir <workspace>/reports/comparison-v1
```

Pass one `--result environment=path` per result and use a new or empty output
directory. This helper produces a basic `report.md` table and `report.json` source
digests; it does not automatically produce energy plots, molecular images, or a
scientific narrative. Read its outputs, then complete the research question,
evidence analysis, figures, and conclusions. For other source formats, build a
report dataset directly from the collected materials.

## Images and delivery

For molecular images, use `chemical.render@1` with input role `geometry=<XYZ file>`
and an environment with the `render` binding. The Job produces SVG, PNG, and a
source-digest record; options include `--style`, `--size`, `--charge`, and
`--multiplicity`. Rendering depicts supplied coordinates; an image does not
establish optimization, connectivity, or transition-state validity.

Use file and scripting tools to assemble existing results; additional scientific
calculations use `job_*`. Plot with an available library, and run rendering Jobs
in their configured environments. Open the final document and images to check
links, axes, captions, units, tables, and provenance. Register the report and its
figures, data, and scripts as materials and cite them in the research conclusion.
The report Skill owns delivery decisions: whether a message is progress, report-ready,
failed, ambiguous, or complete; which report package members may be attached; how
scientific status and limitations are worded; and how the delivery is registered in
research records. Read [report email delivery](references/report_email_delivery.md)
for that contract. After preparing that domain request and receiving explicit
sending authorization, call the generic [email transport Skill](../../../../skills/email/SKILL.md).

The report-specific adapter is `scripts/email_delivery.py`; it converts a
report request into the generic email message and owns report-journal
registration after the transport returns.

## Energy-analysis datasets

For collected `chemical-thermochemistry-result/1`,
`chemical-free-energy-ensemble-result/1`, `chemical-energy-profile-result/1` and
`chemical-scan-slice-result/1`, consume result JSON together with the accompanying
CSV. See [energy contracts](../energetics/references/energy_execution.md).
Show missing quantities as unavailable, preserve E/H/G labels, conditions and
reference, and cite source digests/Artifacts. Plot successful scan rows only,
retain gaps at excluded points, and label profiles as discrete states or sampled
potential slices. Neither an activation comparison nor an ensemble population
certifies TS connectivity, network selectivity or exhaustive sampling.

For conditional kinetic outputs, label TST assumptions, common-precursor branch
scope and the network's temperature, initial concentrations, conservation/error
diagnostics and terminal status. Partial trajectories do not establish the
requested endpoint yield. Distinguish kinetic predictions from product-G rankings.
For electronic/crossing outputs, show target vs reference energy and separate
state-character continuity, numerical stationarity and curvature. An unverified
state or missing Hessian must remain visible in the report.

Use independent `chemical.trajectory@1` and `chemical.research-report@1` Jobs for fixed-camera GIF/XYZ/CSV profiles and illustrated Markdown packages. They retain incomplete paths, supplied author assessment and source evidence; energy comparisons are recomputed through the existing energetics contract. See [trajectory and report contracts](references/research_tools.md).

When available, include the generic `research-review/1` projection as the
`research_review` field in the report input. The report validates its digest and
retains the Review as a bounded index of source references, contradictions and
uncertainties. It is an orientation aid; read the cited Result and Artifact
records before making chemical or completion claims.
