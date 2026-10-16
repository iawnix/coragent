# Candidate-generation script layout

The scripts are grouped by operation and execution role:

- `scripts/path/` prepares mapped endpoints, QST inputs and shared path contracts.
  Validation owns a separate IRC input preparer under `validation/scripts`; it does not import candidate-generation path code.
- `scripts/search/` orchestrates QST, bounded scans and gradient evidence.
- `scripts/backends/` adapts Gaussian and xTB calculators to the shared path
  contract; it does not define the scientific operation's scope.
- `scripts/neb/` owns the ASE/NEB calculator loop and its CLI.
- `scripts/da/` contains the local legacy Diels–Alder geometry helper only.
  It is an optional strategy, not a general reaction restriction.

Root-level forwarding scripts are removed. Jobs and executors must use the
categorized paths directly and include the corresponding module paths in their
staging closure.
