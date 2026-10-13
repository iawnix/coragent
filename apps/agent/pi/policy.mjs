import { existsSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { basename, isAbsolute, join, relative, resolve } from "node:path";

// The retired ExtensionAPI path enforced this policy in its tool_call hook.
// The Harness has no ExtensionAPI, so keep the security boundary as a small,
// presentation-independent hook that can run for every client (TUI, phone,
// monitor, or another trusted client).
export const PACKAGE_READ_TOOLS = Object.freeze(["read", "grep", "find", "ls"]);

export function createPackageSourceReadGuard({
  packageRoot,
  cwd = process.cwd(),
  publicKnowledgeRoots = [],
  publicResourceFiles = [],
}) {
  const root = canonicalPath(packageRoot);
  const publicRoots = publicKnowledgeRoots.map(canonicalPath);
  const publicFiles = new Set(publicResourceFiles.map(canonicalPath));
  function publicAlias(target) {
    if (existsSync(target) || !isWithin(root, target)) return undefined;
    // Models sometimes reconstruct the conventional <package>/skills/<name>
    // path even when a domain Skill is registered from another tree. Treat
    // that spelling as a read-only alias to the exact installed Skill root.
    for (const publicRoot of publicRoots) {
      const aliasRoot = join(root, "skills", basename(publicRoot));
      if (!isWithin(aliasRoot, target)) continue;
      const mapped = canonicalPath(join(publicRoot, relative(aliasRoot, target)));
      if (existsSync(mapped) && (isWithin(publicRoot, mapped) || publicFiles.has(mapped))) return mapped;
    }
    return undefined;
  }
  function rewriteArguments(toolName, args) {
    if (toolName === "job_start" && Array.isArray(args.command)) {
      let changed = false;
      const command = args.command.map(argument => {
        if (typeof argument !== "string" || !isAbsolute(argument)) return argument;
        const mapped = publicAlias(canonicalPath(argument));
        if (!mapped) return argument;
        changed = true;
        return mapped;
      });
      return changed ? { ...args, command } : undefined;
    }
    if (!PACKAGE_READ_TOOLS.includes(toolName)) return undefined;
    const rawPath = typeof args.path === "string" && args.path.trim() ? args.path.trim() : "";
    const target = resolveToolPath(rawPath || cwd, cwd);
    const mapped = publicAlias(target);
    return mapped ? { ...args, path: mapped } : undefined;
  }
  function missingResource(target) {
    if (!isWithin(root, target) || existsSync(target)) return undefined;
    const segments = target.split(/[\\/]/);
    const matches = publicRoots.filter(path => segments.includes(basename(path)));
    return { block: { reason: JSON.stringify({ code: "skill_resource_not_found", path: target,
      message: "This path does not exist. Copy the exact Skill location; resolve its scripts and references relative to that directory.",
      skill_locations: (matches.length ? matches : publicRoots).map(path => resolve(path, "SKILL.md")),
    }) } };
  }
  return (event) => {
    if (!event) return undefined;
    const args = event.args && typeof event.args === "object" && !Array.isArray(event.args) ? event.args : {};
    const rewritten = rewriteArguments(event.toolName, args);
    if (rewritten) return { arguments: rewritten };
    // Reject a provably missing installed resource before allocating a Job.
    // Relative argv paths belong to staged Job inputs and are not package reads.
    if (event.toolName === "job_start" && Array.isArray(args.command)) {
      for (const argument of args.command) {
        if (typeof argument !== "string" || !isAbsolute(argument)) continue;
        const blocked = missingResource(canonicalPath(argument));
        if (blocked) return blocked;
      }
      return undefined;
    }
    if (!PACKAGE_READ_TOOLS.includes(event.toolName)) return undefined;
    const rawPath = typeof args.path === "string" && args.path.trim() ? args.path.trim() : "";
    const target = resolveToolPath(rawPath || cwd, cwd);
    const missing = missingResource(target);
    if (missing) return missing;
    if (!isWithin(root, target) || publicRoots.some(path => isWithin(path, target)) || publicFiles.has(target)) return undefined;
    return {
      block: {
        reason: [
          "TS package implementation and tests are not usage documentation in the installed research runtime.",
          "Use the registered tool schema and research_read with an exact ref,",
          "or the listed Skill locations and their references/scripts. Diagnose or change package implementation",
          "from the separate authored checkout, then build and install a validated release.",
        ].join(" "),
      },
    };
  };
}

function resolveToolPath(value, cwd) {
  let expanded = value;
  if (value === "~") expanded = homedir();
  else if (value.startsWith("~/")) expanded = resolve(homedir(), value.slice(2));
  return canonicalPath(isAbsolute(expanded) ? resolve(expanded) : resolve(cwd, expanded));
}

function canonicalPath(path) {
  if (!existsSync(path)) return resolve(path);
  try {
    return realpathSync.native(path);
  } catch {
    return resolve(path);
  }
}

function isWithin(root, target) {
  const child = relative(root, target);
  return child === "" || (!child.startsWith("..") && !isAbsolute(child));
}
