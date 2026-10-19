# Chemical regression and independent evaluation

The reaction structures, mappings, expected bond changes, synthetic solver output,
and expected verdicts in `tests/` are development fixtures. This includes ts001
and the other cases used to revise chemistry Skills. They test software behavior;
passing them is not independent evidence of reaction-mechanism or TS-search ability.
The release inventory excludes `tests/` and local test state.

For an independent evaluation, freeze the Skill and executable versions first.
Use cases that have not informed those versions, and run the installed package in
a fresh workspace/session with only the intended user inputs. Keep expected
structures, mappings, mechanisms, and outcomes outside that agent's accessible
files and memory. Record the inputs, versions, available tools, calculation
budget, and primary solver evidence with the result.

Once a case informs a prompt, Skill, algorithm, or fix, keep it as a development
regression and use a new held-out case for independent evaluation. Removing its
answer from the current package does not restore its held-out status.
