---
name: geometry-safety
description: Apply a cross-task coordinate safety screen before electronic-structure jobs while allowing declared non-equilibrium reaction-center geometry.
---

# Geometry safety

Use this skill when a coordinate set is about to enter Gaussian, xTB, QST, NEB,
or another electronic-structure calculation, or when a failed path image needs
an objective geometry screen.

This skill is an input-safety check, not a transition-state validator. It must
reject non-finite coordinates, atom identity/order errors, nuclear collapse and
severe non-reaction short contacts. It must allow forming and breaking bonds,
angles and coordination in the declared reaction center to be non-equilibrium.
Never impose equilibrium bond lengths or ordinary-minimum angles on a TS seed.

Use the deterministic shared checker in `skills/_shared/geometry_safety.py`.
For a raw Gaussian input, assess every explicit Cartesian geometry block. An
`Geom=AllCheck` input has no assessable coordinates in the text and must be
reported as `not_assessed` for that part; do not claim that it passed.

The result has two separate meanings:

- `verdict=unsafe`: do not start the calculation; retain the hard failures;
- `verdict=safe`: the coordinates are not obviously broken, but they are not a
  minimum, a saddle, or a mechanistic conclusion.

Reaction pairs may be exempt from the non-bonded short-contact threshold, but
never from the absolute collapse threshold. Supply zero-based reaction-pair
indexes when the reaction context is known. Keep the profile appropriate to the
input (`general`, `reaction_seed`, `ts_candidate`, or `path_image`).

This skill does not impose a research sequence. The Agent may choose QST, NEB,
scan, direct TS optimization, or diagnostics based on the current evidence. It
only prevents an obviously damaged coordinate set from being passed to a
solver and records warnings for non-equilibrium reaction-center geometry.

For the schema and CLI contract, read [geometry_safety.md](references/geometry_safety.md).
