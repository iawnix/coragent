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

The files directly under `scripts/` are compatibility entrypoints for existing
Jobs and callers. They execute the implementation in the corresponding
subdirectory; they are not a second implementation. New executor declarations
should reference the categorized file and list its categorized module path.
