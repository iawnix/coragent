# Chemical execution environments

[简体中文](README.zh-CN.md)

These installation resources are separate from the Host control environment.
They are explicit Conda locks with SHA-256 package hashes, for Linux x86_64.
`wrapper.lock` requires glibc >=2.17; the scientific/rendering locks require
glibc >=2.28. CF22D uses a generic x86_64 PySCF build rather than the build
optimized for the maintainer's CPU. Other targets need their own verified lock.

| Lock | Bindings | Contents |
| --- | --- | --- |
| wrapper.lock | Gaussian/xTB/CREST Python wrappers | Python 3.11 and packaging tools; native solvers are installed separately |
| structure.lock | structure, validation | RDKit, NumPy, Matplotlib and Pillow for geometry/trajectory/report analysis |
| path.lock | path_xtb, path_gaussian | Structure dependencies plus ASE 3.29.0 and SciPy for NEB v2 |
| cf22d.lock | pyscf | PySCF, geomeTRIC and PySCF dispersion, all from Conda |
| render.lock + render.requirements.txt | render | RDKit, Cairo, Matplotlib, xyzrender and its rendering dependencies |

The basic text report helper uses the Host's standard library. Illustrated report/trajectory Jobs use `structure`; neither needs `render.lock`.
Rendering's notebook dependencies are upstream xyzrender requirements; they
are confined to the rendering target. No environment includes the CoRAgent wheel.

Declare the absolute Python prefix, lock and native solver paths in `config.toml`
under the platform or scheduler entry's `bindings`, then prepare those versioned
environments independently on their execution hosts. The main installer validates configured
bindings; an unconfigured installation creates neither a scientific environment
nor a Qrun queue.

The target-local helper consumes explicit bindings:

```bash
python3 -B /ABS/package-root/packaging/coragent_packaging/installer/install_job_environment.py \
  --config /ABS/execution.toml --platform PLATFORM --scheduler-entry ENTRY --backend structure
```

Replace `/ABS/package-root` with the absolute CoRAgent package directory
available on the execution host. `/ABS/execution.toml` is a copy accessible on that
host of the execution-only file generated from the main configuration
(`execution.schema_version = 2`). The selected binding's `conda_executable`,
`prefix` and `lock_ref` paths must be valid on that host. Maintain those bindings
in the main `config.toml` and regenerate the copy after changes.
Run the helper on the execution host; a controller Python path is not a remote
environment. `wrapper` provides Python for configured
Gaussian/xTB/CREST wrappers, while their native binaries remain operator-provided.
Use a dedicated, versioned prefix. The helper records verified environment
ownership and inventory; it does not activate a CoRAgent release or submit an
acceptance Job. Structure and validation may share a prefix. CF22D needs no
activation script or `LD_PRELOAD` workaround.

The main configuration is authoritative; `generated/job.toml` is a derived input.
Online PubChem/OPSIN lookup is optional and has no automatic installation default.
Configure `[name_resolver]` explicitly and bind `CORAGENT_NAME_RESOLVER_CONFIG`
in the structure backend to a path readable on the selected platform. Local
preparation may feed a remote calculation without enabling name lookup on every
platform. Supplied structures do not require this service.

The structure acceptance check validates RDKit and geometry generation without
requiring a resolver configuration. `--verify-job-target PLATFORM/ENTRY` requests
bounded acceptance Jobs during installation. Reports distinguish environment
checks from actual execution; offline acceptance does not contact name services.

Installation never solves dependencies again. Pinned pip artifacts download
to a cache below the environment parent and install with `--require-hashes`
and `--no-deps`; `pip check` verifies dependency completeness. The helper's
`--package-cache` selects another artifact directory and `--offline` uses only that directory and
the Conda cache (`CONDA_PKGS_DIRS`). Locks and release files remain read-only.
An interrupted new prefix is removed; an existing prefix is never updated in
place. `--adopt` explicitly verifies a previously seeded environment against
the locks before publishing its receipt.

After configuring the bindings, run the installed control interpreter's
`-m research_agent.application.environment_check --config "$CORAGENT_JOB_CONFIG"`. This checks
the actual configured target and declared imports, including SSH targets.
Then execute a bounded scientific Job: matching package inventories and imports
alone do not prove a solver or method works.

For a lock refresh, solve the documented root requirements from conda-forge
in an isolated environment using `CONDA_OVERRIDE_ARCHSPEC=x86_64`, export
`conda list --explicit --sha256`, and validate a new installation plus actual
calculations before publishing the new lock. Fixed pip entries must include
the hashes of their upstream artifacts. Do not export credentials, add a
local-only wheel, or replace the lock of a running installation in place.

The optional `path` profile uses path.lock for explicitly configured
`path_xtb` / `path_gaussian` native bindings. It provides RDKit/NumPy, ASE and SciPy for scans,
gradients and ASE NEB v2 without changing the existing lightweight wrappers. For example,
configure `[execution.platforms.local.bindings.path_xtb]` with `command = "/opt/xtb/bin/xtb"`
(and activation_script if needed), bind a prefix based on `path.lock`, and prepare
that backend with the target-local helper. This profile has no default native scientific smoke calculation; the selected
recipe's environment check and an explicit bounded scientific Job are separate.

Gaussian numerical parsing uses pinned cclib 1.8.1 through the wrapper, structure and path `.requirements.txt` supplements; wrapper/structure also add SciPy. Provision a new immutable environment when updating. cclib extracts numerical data; it does not decide optimization phases, IRC completeness or chemical connectivity.
