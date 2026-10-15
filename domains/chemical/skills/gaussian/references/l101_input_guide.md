# Gaussian L101 errors and input-file guide

## Contents

- [What this error means](#what-this-error-means)
- [Minimal standard input structure](#minimal-standard-input-structure)
- [Charge and spin multiplicity](#charge-and-spin-multiplicity)
- [Two ways to write geometry](#two-ways-to-write-geometry)
- [Route-dependent additional sections](#route-dependent-additional-sections)
- [Multistep jobs (Link1)](#multistep-jobs-link1)
- [Priority order for diagnosing L101](#priority-order-for-diagnosing-l101)
- [Practical input-file checklist](#practical-input-file-checklist)
- [Explicit Gaussian inputs in TSPi](#explicit-gaussian-inputs-in-tspi)
- [Minimizing a failed input](#minimizing-a-failed-input)

## What this error means

Gaussian's `L101` (Link 101) reads basic input related to the molecule and job
control at the start of a calculation. The keywords in the route section decide
which later sections L101 expects. Common contents include:

- a title line;
- total charge and spin multiplicity;
- Cartesian coordinates or a Z-matrix;
- variables, basis sets, ECPs, or ModRedundant data required by the route.

The route section (the method, basis, and task keywords beginning with `#`) is
processed earlier. A misspelled route keyword or an unsupported combination can
also make L101 enter the wrong input-reading mode. If `L101`, `RdGeom`,
`charge`, `multiplicity`, `symbol`, `z-matrix`, or `geometry` appears before
`Error termination via Lnk1e`, the most common cause is malformed or incomplete
input. `L101` is the name of an input-reading stage, not a particular chemical
calculation error.

There is an important boundary. If the input asks Gaussian to read geometry or
an electronic state from a checkpoint, a missing, incompatible, or damaged
checkpoint can also fail near L101. A route that activates an unsuitable
additional-input mode can look like an input parsing error as well. Inspect the
first concrete diagnostic before L101 instead of treating the final `Lnk1e`
line as the cause.

This guide covers creating and checking inputs according to Gaussian's public
input format. It does not discuss Gaussian source code, binaries, or internal
implementation details.

## Minimal standard input structure

A normal single-step job usually has the following order. Keep a blank line
between sections; the file normally retains a blank line after the final data
line, which means two newline characters at the end.

```text
%chk=water.chk
%mem=2GB
%nprocshared=4
#p B3LYP/6-31G(d) Opt

Water geometry optimization

0 1
O    0.000000   0.000000   0.000000
H    0.000000   0.757000   0.586000
H    0.000000  -0.757000   0.586000

```

The sections mean:

1. Lines beginning with `%` are optional job-control lines such as checkpoint,
   memory, and processor settings.
2. Lines beginning with `#` form the route section, which ends at a blank line.
3. The first section after the route is the title. It must have its own section.
4. The first line after the title is total charge and spin multiplicity, such as
   `0 1` for a neutral singlet.
5. Geometry follows. A Cartesian line normally contains an element symbol and
   three coordinates.
6. Whether more data follows the geometry depends on the route keywords. With
   no additional data, end the file with a blank line.

If the blank line after the route or title is missing, or if the coordinate
block has no terminating blank line, later text can be read as coordinates or
additional data and produce an L101 error.

## Charge and spin multiplicity

Write charge and multiplicity as two integers separated by whitespace:

```text
0 1    # neutral singlet
1 2    # +1 cation doublet
-1 1   # -1 anion singlet
```

Check the following:

- Include the correct sign for the charge. Do not put `+1`, `singlet`, or prose
  on this line.
- The multiplicity is a positive integer consistent with `2S+1`; never use zero
  or a negative value.
- The electron count must be compatible with the selected multiplicity. An even
  electron system generally cannot be assigned a closed-shell singlet when the
  electron count and state disagree. Set the actual state for radicals, ions,
  and metals.
- ONIOM, QST, multicomponent, or external-charge inputs can have additional
  charge/multiplicity lines. Follow the format for the selected keyword rather
  than merging those lines arbitrarily.

## Two ways to write geometry

### Cartesian coordinates

The safest basic form has one atom per line:

```text
0 1
C    0.000000   0.000000   0.000000
O    1.200000   0.000000   0.000000
H   -0.600000   0.900000   0.000000
H   -0.600000  -0.900000   0.000000
```

Notes:

- Element symbols must be valid, such as `C`, `Cl`, or `Si`, with the casing
  supported by Gaussian.
- The three coordinates must be finite numbers. Use whitespace separators and
  do not include unit strings, `NaN`, or `*****`.
- Atom order matters for constraints, scans, QST, IRC, and result analysis. If
  you change it, update every atom index that refers to it.
- `Bq` is a ghost center, and `X` or `-` can be used for some Z-matrix or dummy
  center cases. Use them only when required; they are not ordinary elements.
- End the coordinate block with a blank line. Basis, ECP, or ModRedundant data
  must not be attached directly to the final coordinate line.

### Z-matrix

In a Z-matrix, each new atom may reference only atoms already defined. For
example:

```text
0 1
O
H  1  R
H  1  R  2  A

R = 0.96
A = 104.5

```

Commonly, the second atom needs a previously defined atom and a bond length; the
third also needs a bond angle; and later atoms usually need a dihedral angle.
Variable names must be defined in the following variable section and must not
be misspelled or defined twice.

Common Z-matrix causes of L101 include references to atoms that have not yet
appeared, missing bond-length/angle/dihedral fields, mixing Cartesian and
Z-matrix fields on one line, undefined variables, and a collinear first three
atoms that cannot define a dihedral.

If no variables are needed, end the geometry with a blank line. If variables are
used, terminate the variable section with another blank line.

## Route-dependent additional sections

Do not inspect geometry alone. Check whether the route enables keywords that
require more input. Common examples are:

| Route or situation | Possible data after geometry | Common L101 mistake |
|---|---|---|
| `Gen`, `GenECP` | Element-grouped basis and/or ECP data | Missing `****`, mismatched element names, or wrong section order |
| `Opt=ModRedundant` | Constraint, freeze, or scan definitions | Out-of-range atom index, wrong field count, or missing final blank line |
| `QST2`, `QST3` | Two or three complete structures | Wrong number of structures, different atom order/count, or missing separator |
| `IRC`, `Scan`, etc. | Control lines required by the keyword | Treating control lines as coordinates or putting them in the wrong section |
| `Geom=AllCheck`, `Guess=Read` | Data read from a checkpoint | Missing/incompatible checkpoint or conflicting inline sections |
| ONIOM, external point charges | Layer, link-atom, or charge data | Wrong format, atom number, layer marker, or data order |

Use the user guide for the selected Gaussian version for exact additional-section
syntax. Do not add data merely to fill out the file; a section not required by
the route can itself be misread by L101.

## Multistep jobs (Link1)

Each section of a multistep input must independently satisfy its own format and
be separated with `--Link1--`:

```text
%chk=water.chk
#p B3LYP/6-31G(d) Opt

Optimize

0 1
O  0.0  0.0  0.0
H  0.0  0.8  0.6
H  0.0 -0.8  0.6

--Link1--
%chk=water.chk
#p B3LYP/6-31G(d) Freq Geom=AllCheck

Frequency from checkpoint

```

When the second section uses `Geom=AllCheck`, whether geometry, charge, or
multiplicity should be omitted depends on the checkpoint mode. Do not copy the
first section's coordinates mechanically into every section. Each route,
checkpoint, and electronic state must agree.

## Priority order for diagnosing L101

When L101 appears, the following order is more effective than changing the
method or adding resources immediately:

1. **Locate the first concrete message.** Find the first `Error`, `Erroneous`,
   `Unrecognized`, `End of file`, or geometry/charge diagnostic before L101. The
   final `Lnk1e` line is only a termination summary.
2. **Check section boundaries.** Confirm blank lines between route, title,
   electronic state, coordinates, and additional data, including a final blank
   line after the last coordinate.
3. **Check the electronic state.** Recompute total charge, multiplicity, and
   electron count. Make sure a title, comment, or old job's charge line was not
   read as the electronic state.
4. **Check coordinates.** Verify element symbols, three numeric columns, atom
   count, atom order, finite values, and obvious zero-distance overlaps.
5. **Check Z-matrix or constraints.** Every reference must point to an atom
   already defined, every variable must be defined, and every index must be in
   range.
6. **Check route-triggered input.** Temporarily remove unnecessary `Gen`,
   `ModRedundant`, external-charge, or complex checkpoint options, then add them
   back one at a time after a minimal input reads successfully.
7. **Check checkpoint dependencies.** For `AllCheck`, `Guess=Read`, and
   `Geom=Checkpoint`, confirm that the file exists, is readable, and belongs to
   a compatible system and calculation.
8. **Compare a minimal runnable case.** Run a simple molecule or single point
   with the same method/basis, then add optimization, frequency, constraints,
   and multistep settings incrementally.

## Practical input-file checklist

Before submission:

- [ ] Use plain text; avoid rich-text files, BOMs, smart quotes, and invisible control characters.
- [ ] Use resource lines such as `%chk`, `%mem`, and `%nprocshared` in syntax supported by the target Gaussian version.
- [ ] Start the route with `#` and check method, basis, and task spelling.
- [ ] Include a title section after the route and a blank line after the title.
- [ ] Write charge and multiplicity as the correct two integers.
- [ ] Keep atom-line formats consistent and coordinates finite.
- [ ] Reference only defined atoms in a Z-matrix and define every variable.
- [ ] Supply required `Gen`, ECP, ModRedundant, QST, ONIOM, or external-charge sections in the correct order.
- [ ] Ensure every Link1 section is independently interpretable and separated by `--Link1--`.
- [ ] End the file with a blank line; do not stop immediately after the final data character.
- [ ] Record the actual input and output files. During diagnosis, use the route, charge, multiplicity, and coordinates echoed in the output.

## Explicit Gaussian inputs in TSPi

When submitting a `.gjf` through TSPi's explicit-input executor, the file must
still follow Gaussian syntax. The executor does not add a title, electronic
state, coordinates, or additional sections to the route. Check the L101 items
before starting the Job.

Use `chemical.gaussian-input@1`. The `--validation` option selects a later check
type; it does not add keywords to the input. For example:

```bash
"$CORAGENT_PYTHON" -m research_agent.application.executors \
  --config "$CORAGENT_JOB_CONFIG" --environment local \
  --executor chemical.gaussian-input --version 1 \
  --input input=water.gjf --output prepared/water.json -- \
  --method B3LYP --basis '6-31G(d)' --charge 0 --multiplicity 1 \
  --threads 4 --memory-mb 2000 --validation opt
```

Successful preparation only means that the request and input format were
accepted; Gaussian has not necessarily terminated normally. Inspect the actual
output for the echoed route, convergence information, and
`Normal termination of Gaussian`.

## Minimizing a failed input

When an original input is complex, copy it to a new file and build a minimal
case in this order:

1. Keep only `%chk`, a simple route, title, correct charge/multiplicity, and
   Cartesian coordinates.
2. Run a single point first; add `Opt`, `Freq`, or another task after it succeeds.
3. Add one additional section at a time, such as `ModRedundant` or `Gen`.
4. Keep a new filename and output at each step so the section that introduced
   L101 can be identified.

This separates input parsing failures from later SCF convergence, geometry
optimization, or resource problems. Only after the input has been read
successfully is it useful to diagnose the SCF or optimization algorithm.
