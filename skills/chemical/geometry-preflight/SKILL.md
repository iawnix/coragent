---
name: geometry-preflight
description: Screen coordinates before electronic-structure work while preserving declared non-equilibrium reaction-center geometry.
---

# Geometry preflight

[Chinese version](SKILL.zh-CN.md)

## Script routing

Select the executor in [Operation entrypoints](references/commands.md), then read the matching input and validation contract in this Skill. Ordinary invocation does not require source inspection; unlisted files under `scripts/` are internal helpers.

Screen candidate coordinates before Gaussian, xTB, CF22D, QST, NEB, or a restart frame enters a solver. The standalone executor accepts a `chemical-geometry-safety-input/1` JSON object containing elements, Cartesian coordinates in angstrom, and known reaction/connectivity context. It does not accept an XYZ or GJF file directly. It catches non-finite coordinates, atom/coordinate count mismatches, nuclear collapse, and severe non-reaction contacts while allowing deliberate forming/breaking bonds in a TS seed.

## Profiles and inputs

Choose `general`, `reaction_seed`, `ts_candidate`, or `path_image` in the JSON. When a reaction context is known, provide zero-based reaction-pair indexes so the checker can distinguish a forming contact from an accidental clash. Supply known bonded pairs and reference coordinates when checking an edited pose; absent connectivity or a reference limits the diagnosis.

Save the JSON shown in [geometry safety](references/geometry_safety.md) as `<work_dir>/geometry-check.json`, then prepare `chemical.geometry-safety@1`:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors --config "$CORAGENT_JOB_CONFIG" --executor chemical.geometry-safety --version 1 --input "input=<work_dir>/geometry-check.json" --output "<work_dir>/prepared/geometry-check.json"
```

Use the actual work directory returned by `research_create` or `research_read`. The preparer returns `request_file` and `request_sha256`; it has not run this standalone check. Submit those values:

```text
job_start({"node_id":"<node_id>","request_file":"<returned request_file>","request_sha256":"<returned request_sha256>"})
```

Read the completed Job's `results/result.json`. It contains `safe`/`unsafe`, hard failures, warnings, and per-check status including `not_assessed`. A completed checker Job can report `unsafe`; inspect the report before using the candidate. `safe` means no covered hard failure was found. It does not establish chemically suitable angles, correct structure identity, a convergent solver input, or a validated TS.

Explicit Gaussian inputs use [the Gaussian Skill](../gaussian/SKILL.md): `chemical.gaussian-input@1` checks explicit Cartesian blocks during request preparation and again before launching Gaussian. `Geom=AllCheck` has no text coordinates to assess; check the source checkpoint geometry separately. Generic Bash execution does not apply these Gaussian checks.

Read [geometry safety](references/geometry_safety.md) for fields, thresholds, and coverage. After `reactive-geometry` edits, check the revised coordinates again and retain the report as candidate evidence. Preserve optimized fragment geometry when positioning reactants; do not straighten an internal fragment angle merely to align a transfer coordinate.
