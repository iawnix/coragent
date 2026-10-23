# Strategy Reflection

Use this reference when repeated results challenge the current plan. Reflection
helps Root revise the hypothesis, method, or next research question.

## Questions

- Is the target elementary step or hypothesis itself wrong?
- Are conformer, orientation, atom map, charge, spin, state, or environment
  assumptions incomplete?
- Does the method represent the relevant electronic structure?
- Is a constrained seed being mistaken for a stationary point?
- Do IRC endpoints remain finite or repeatedly reach the same basin?
- Are several sites, spin states, pathways, or dynamic outcomes plausible?
- Is the observed anomaly evidence against the current framing rather than a
  calculation nuisance?

## Response

Use the existing node_id. Record observations, scientific criteria and next-step decisions in a research_update note, or publish a reusable conclusion with research_result, citing collected materials and limitations. Do not duplicate the same finding in both records or task progress. A completed computation does not establish a scientific conclusion or require a new Node or Result.

For excited-state, open-shell, metal, radical, crossing, bifurcating, or
non-adiabatic problems, state the relevant electronic-state and dynamics
criteria explicitly and select methods that can evaluate them.

Ask for independent Review when a bounded counterargument would help. The Root
must still respond and own the next decision.

Before changing a mechanism after a failed run, use [search recovery](../../method-selection/references/search_recovery.md) to classify the evidence. Route mismatch calls for input/binding diagnosis; complete repeated same-basin IRC calls for a mode/candidate/hypothesis review. Distinguish these from incomplete paths. Compare concerted versus stepwise routes, proton relays, solvent/catalyst participation, conformers, spin and competing sites with discriminating calculations. Local proximity thresholds are not a mechanism classifier, and no fixed retry count replaces evidence.
