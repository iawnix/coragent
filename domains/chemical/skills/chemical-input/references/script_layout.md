# Chemical-input script layout

The implementation is split by the scientific operation it supports:

- `scripts/materials/` imports materials and resolves names. `material.py`,
  `analysis_material.py` and `name_resolution.py` are material contracts and
  provenance handling.
- `scripts/reaction/` handles reaction identity and geometry-independent
  preparation: `correspondence.py`, `conformers.py` and `prepare.py`.
- `scripts/geometry/` contains structure comparison orchestration.
- `scripts/diagnostics/` contains local geometry observations and their Job CLI.
- `scripts/tensor/` contains Cartesian tensor reordering.

Root-level forwarding scripts are removed. Jobs and callers must use the implementation
in the corresponding categorized subdirectory and include the corresponding module paths.
