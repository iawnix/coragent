# xTB backend contract

`chemical.xtb@1` translates chemical-material/1 fields to the configured GFN2-xTB
binding for `sp`, `opt` and `opt-sp`. It records the native command, charge,
spin, solvent/state fields, output digests and parser status. The parser accepts
only the documented artifact forms; unsupported native task output remains raw
and unclassified.

The path adapters `chemical.scan-xtb@1`, `chemical.gradient-xtb@1` and
`chemical.neb-xtb@2` use the optional `path_xtb` binding under
`candidate-generation`. They own their restraint, gradient and NEB evidence
contracts. This backend contract does not select an operation or interpret its
scientific result. Native command examples are in [operation recipes](../../method-selection/references/xtb_operation_recipes.md).
