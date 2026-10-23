# Backend Selection

The Root Agent selects a backend from the scientific question, uncertainty,
system size, electronic structure, desired observable, available artifacts,
cost, and live environment. Use the Skill instructions to check accepted tasks
and parameters.

Consider:

- whether the method can represent charge, spin, excited state, metal center,
  multireference character, solvent, and constraints;
- whether the task produces the research note needed to discriminate hypotheses;
- candidate quality and atom mapping;
- whether lower-cost exploration is scientifically informative rather than only
  cheaper;
- whether a higher-level recalculation is needed for robustness;
- live local/remote software and scheduler readiness.

Gaussian's explicit-input runner can execute supplied TS, scan or QST inputs
and follow-up calculations; it does not construct a complete mechanism study.
xTB/CREST and ASE NEB may suit exploration, but distinguish scientific suitability
from an available execution path. The bundled xTB runner supports opt/SP only;
CREST, NEB and external crossing tools need a verified installed command or
concrete script through generic Job Manager. Check shared runners and installed
tools before declaring a capability unavailable. Choose their order from the research question.

Record the method choice and falsifiable purpose in the existing Node's plan and preserve
changes of approach in notes. A different backend or recalculation stays within the same
question. Create another Node only for a new research objective needing its own continuing
investigation and judgment; publish a Result when there is a conclusion worth citing.
