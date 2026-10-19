---
name: geometry-preflight
description: Screen coordinates before electronic-structure work while preserving declared non-equilibrium reaction-center geometry.
---

# Geometry preflight

[Chinese version](SKILL.zh-CN.md)

Run this check on an XYZ or Gaussian input before Gaussian, xTB, CF22D, QST, NEB, or a restart frame enters a solver. It catches non-finite coordinates, atom/header mismatches, nuclear collapse, and severe non-reaction contacts while allowing deliberate forming/breaking bonds in a TS seed.

## Profiles and inputs

Choose `general`, `reaction_seed`, `ts_candidate`, or `path_image`. When a reaction context is known, provide zero-based reaction-pair indexes so the checker can distinguish a forming contact from an accidental clash. For Gaussian text, assess every explicit Cartesian block; a `Geom=AllCheck` section has no coordinates to screen and is recorded as not assessed.

Use the shared checker `skills/_shared/geometry_safety.py` through `chemical.geometry-safety@1`:

```text
--input <xyz-or-gjf> --output <report.json>
```

The result gives hard failures, warnings, reaction-pair exemptions, profile, and a `safe`/`unsafe`/`not_assessed` verdict. A `safe` result authorizes solver input preparation, while optimization, mode, IRC, and structure assessment provide the scientific interpretation.

Read [geometry safety](references/geometry_safety.md) for schema, thresholds, and Gaussian block handling. After `reactive-geometry` edits, run this check again and carry the report digest into the candidate Job.
