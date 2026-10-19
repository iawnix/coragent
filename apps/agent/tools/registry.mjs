import { createResearchTools } from "./research/tools.mjs";
import { createJobTools } from "./jobs/tools.mjs";
import { createArtifactTools } from "./artifacts/tools.mjs";

/** One registry, one session-owned Python bridge, no dynamic factory manifest. */
export function createCoreTools({ commandBridge, getTaskBinding, getResearchTaskId, bindResearchNode }) {
  return [
    ...createResearchTools({ commandBridge, getResearchTaskId, bindResearchNode }),
    ...createJobTools({ commandBridge, getTaskBinding }),
    ...createArtifactTools({ commandBridge }),
  ];
}
