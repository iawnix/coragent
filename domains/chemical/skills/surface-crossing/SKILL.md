---
name: surface-crossing
description: Search and check regular crossings of two distinct-spin Gaussian HF/DFT surfaces, with energy-gap, projected-gradient and optional seam-curvature evidence.
---

# Different-spin surface crossings

[中文说明](SKILL.zh-CN.md)

Use `chemical.mecp-gaussian@1` for a bounded crossing candidate search and
`chemical.crossing-check@1` for independent numerical evidence. Read the
[contracts and scientific scope](references/crossing_execution.md) first.
The native solver uses the optional `path_gaussian` binding; the checker uses
`structure`. Both accept input role `input` and use ordinary Jobs.

A small energy gap alone is insufficient: inspect the projected gradient and
constrained curvature. Keep numerical seam stationarity separate from electronic
state identity, SCF stability and global minimality. Distinct spin multiplicities
and acceptable S² values do not prove continuous wavefunction identity.
This implementation is not QBICS, a same-spin conical-intersection optimizer,
spin-orbit coupling, nonadiabatic dynamics or an ordinary TS/IRC validator.
