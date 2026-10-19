# Molecular preparation

[中文](molecular_preparation.zh-CN.md)

Use `material-preparation` to prepare graphs and correspondence before generating
reaction geometries. Follow its [mapping procedure](../../material-preparation/references/reaction_mapping.md).

1. Resolve names with `chemical.resolve@1`, import SMILES with `chemical.material@1`,
   and inspect graph, formula, charge, and stereo with `chemical.inspect@1`.
2. Establish persistent labels for all reactant atoms, including explicit H, across
   all fragments. For each proposed step, select graph correspondences using
   `chemical.map-candidates@1` and check the supplied mapped reaction and declared
   changes with `chemical.reaction@1`. If products are unknown, retain reactant
   identities and map later hypotheses onto them.
3. Generate each species with `chemical.seed@1` from selected mapped SMILES. Keep its
   per-row atom table with the XYZ through conformer search, optimization, and
   assembly. Preserve supplied coordinates together with their graph correspondence.
4. Explore unspecified stereoisomers, conformers, and approach poses as distinct
   choices. Conformational changes retain the molecular graph and atom labels.
   Assemble path endpoints in a common mapped order and record row permutations.

Prepare these registered operations through the generic executor, submit with
`job_start`, and collect Artifacts into the step record. Pass the selected mapping
and reactive pairs to geometry construction, then use the same labels for mode
interpretation and IRC endpoint comparison.
