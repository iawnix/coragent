import { createReadTool, createWriteTool, createEditTool, createBashTool } from "@earendil-works/pi-durable/tools";
import { loadPi } from "./source.mjs";
import { adaptCodingTool } from "./tool-adapter.mjs";

export async function createCodingTools(cwd, getExecutionSelection = async () => null) {
  const [{ createGrepTool }, { createFindTool }, { createLsTool }, { getToolPath }] = await Promise.all([
    loadPi("grep"), loadPi("find"), loadPi("ls"), loadPi("toolsManager"),
  ]);
  for (const dependency of ["rg", "fd"]) {
    if (!getToolPath(dependency)) throw new Error(`Required coding tool dependency is unavailable: ${dependency}`);
  }
  return [
    ...[createReadTool(), createWriteTool(), createEditTool(), createBashTool()]
      .map(tool => ({ ...tool, executionMode: "sequential", ...(tool.name === "bash" ? {
        async execute(params, api, context) {
          const selection = await getExecutionSelection(context);
          const prefix = selection
            ? `export CORAGENT_TASK_EXECUTION='${JSON.stringify({ ...selection, workspace_root: cwd }).replaceAll("'", "'\\''")}'\n`
            : "unset CORAGENT_TASK_EXECUTION\n";
          return tool.execute({ ...params, command: prefix + params.command }, api, context);
        },
      } : {}) })),
    ...[createGrepTool(cwd), createFindTool(cwd), createLsTool(cwd)].map(adaptCodingTool),
  ];
}
