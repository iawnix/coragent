// Pi's native coding tools use the same compact card presentation as the
// CoRAgent tools. Keep this list next to the client wiring so a newly enabled
// native tool cannot silently fall back to Pi's verbose default renderer.
export const PI_BUILTIN_TOOL_NAMES = Object.freeze([
  "bash",
  "read",
  "write",
  "edit",
  "grep",
  "find",
  "ls",
  // Available from pi-durable on Windows, but not registered by the Linux
  // coding-tools extension today.
  "powershell",
]);
