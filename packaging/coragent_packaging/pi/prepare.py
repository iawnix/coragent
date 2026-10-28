"""Resolve, patch, and verify the Pi v1 durable runtime used by CoRAgent."""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    package_root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(package_root / "packaging"), str(package_root / "backend/src"), str(package_root)]

import argparse, fcntl, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
PIN_PATH = ROOT / "packaging/coragent_packaging/pi/source.json"
PATCH_ROOT = ROOT / "packaging/coragent_packaging/pi/patches"
PATCH_NAMES = ("001-durable-policy.patch", "002-configuration-credentials.patch", "003-proxy-cache-affinity.patch", "004-terminal-input.patch")
class PiSourceError(RuntimeError): pass

def pin():
    value=json.loads(PIN_PATH.read_text())
    if not isinstance(value,dict) or not isinstance(value.get("commit"),str): raise PiSourceError("invalid Pi source pin")
    return value

def git(source,*args):
    try: return subprocess.run(["git","-C",str(source),*args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.strip()
    except (OSError,subprocess.CalledProcessError) as exc: raise PiSourceError(f"cannot inspect Pi source {source}: {exc}") from exc

def verify(source):
    expected=pin()["commit"]
    if git(source,"rev-parse","HEAD") != expected: raise PiSourceError(f"Pi source commit mismatch: expected {expected}")
    required = [
        "packages/durable/src/index.ts", "packages/durable/src/storage/sqlite/node.ts",
        "packages/coding-agent/src/core/model-runtime.ts", "packages/tui/src/index.ts",
    ]
    if any(not (source / path).is_file() for path in required):
        raise PiSourceError("Pi source is missing the public Durable runtime")
    for package in ("ai", "durable", "coding-agent", "tui"):
        version = json.loads((source / "packages" / package / "package.json").read_text())["version"]
        if "v" + version != pin()["tag"]:
            raise PiSourceError("Pi package version does not match the pinned source descriptor")
    if not verify_patches(source):
        raise PiSourceError("Pi patches are missing or incompatible")
    return expected

def patches():
    result = [PATCH_ROOT / name for name in PATCH_NAMES]
    if any(not path.is_file() for path in result):
        raise PiSourceError("missing managed Pi patch files")
    return result

def verify_patches(source):
    """Check the ordered patch stack without mutating the managed checkout.

    Patches can touch the same files.  Each reverse
    check therefore has to run after the later patch has been removed; doing
    independent checks against the final tree rejects a valid stack.
    """
    touched = set()
    for patch in patches():
        for line in patch.read_text().splitlines():
            if line.startswith(("--- a/", "+++ b/")):
                path = line[6:]
                if path != "/dev/null":
                    touched.add(path)
    with tempfile.TemporaryDirectory(prefix=".pi-verify-", dir=source.parent) as temporary:
        checkout = Path(temporary)
        # The repository root is nested in the product checkout, so create a
        # private Git boundary before applying paths from Pi's patch root.
        subprocess.run(["git", "-C", str(checkout), "init", "--quiet"], check=True)
        for relative in touched:
            origin = source / relative
            if origin.is_file():
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origin, target)
        for patch in reversed(patches()):
            if not patch_check(checkout, patch, reverse=True):
                return False
            subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", str(patch)], check=True, text=True)
    return True

def patch_check(source, patch, *, reverse=False):
    result = subprocess.run(
        ["git", "-C", str(source), "apply", "--check", *(["--reverse"] if reverse else []), str(patch)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.returncode == 0

def apply_patch(source):
    if git(source, "rev-parse", "HEAD") != pin()["commit"]:
        raise PiSourceError("refusing to patch a different Pi source commit")
    # Later patches can replace an earlier patch's reverse-check context. A
    # verified complete stack is already applied even when that earlier group
    # no longer reverses independently against the final tree.
    if verify_patches(source):
        return
    # Apply patches in order. Later patches can build
    # on earlier managed patches, so checking every patch against the pristine
    # checkout would reject a valid ordered patch group.
    for patch in patches():
        if patch_check(source, patch, reverse=True):
            continue
        if not patch_check(source, patch):
            raise PiSourceError(f"Pi patch is partially applied or incompatible: {patch.name}")
        try:
            subprocess.run(["git", "-C", str(source), "apply", str(patch)], check=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise PiSourceError(f"failed to apply {patch.name}: {exc}") from exc

def clone(destination):
    p=pin(); destination.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(["git","clone","--no-checkout",p["repository"],str(destination)],check=True)
    git(destination,"fetch","--depth","1","origin",p["commit"]); git(destination,"checkout","--detach",p["commit"])
    apply_patch(destination); verify(destination); return destination

def install(root):
    commit=pin()["commit"]
    from research_agent.bootstrap.layout import paths
    destination=paths(Path(root).resolve()).pi_runtime/commit
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (destination.parent / (commit + ".install.lock")).open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        return _install_locked(destination, commit)


def _install_locked(destination, commit):
    if destination.exists():
        if not (destination/"packages/durable/src/index.ts").is_file(): raise PiSourceError(f"invalid managed Pi source: {destination}")
        try:
            apply_patch(destination)
        except PiSourceError:
            # A prior interrupted or older managed installation may contain a
            # patch stack from a different patch revision. The checkout is
            # installer-owned, so restore the pinned commit before retrying the
            # complete ordered stack.
            subprocess.run(["git", "-C", str(destination), "reset", "--hard", commit], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(destination), "clean", "-fd"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            apply_patch(destination)
        verify(destination)
    else:
        with tempfile.TemporaryDirectory(prefix=".pi-source-",dir=destination.parent) as temp:
            staged=Path(temp)/commit; clone(staged); install_deps(staged); hydrate_model_data(staged); prepare_build(staged); os.replace(staged,destination)
    if not (destination/"node_modules").is_dir(): install_deps(destination)
    hydrate_model_data(destination)
    prepare_build(destination); verify(destination); return destination

def install_deps(source):
    npm=shutil.which("npm")
    if not npm: raise PiSourceError("npm is required")
    subprocess.run([npm,"ci","--ignore-scripts"],cwd=source,check=True,stdout=sys.stderr)

def hydrate_model_data(source):
    """Generate Pi provider model metadata before the offline build.

    The pinned Pi checkout does not commit generated provider data. Its
    offline build validates files such as ``amazon-bedrock.json`` and fails
    without this preparation step.
    """
    data = source / "packages/ai/src/providers/data"
    if (data / "amazon-bedrock.json").is_file():
        return
    npm=shutil.which("npm")
    if not npm: raise PiSourceError("npm is required")
    subprocess.run([npm,"run","hydrate:model-data"],cwd=source,check=True,stdout=sys.stderr)


def prepare_build(source):
    npm=shutil.which("npm")
    if not npm: raise PiSourceError("npm is required")
    if not (source/"packages/chord/dist/index.js").exists() or not (source/"packages/coding-agent/dist/bundle").exists():
        subprocess.run([npm,"run","build:offline"],cwd=source,check=True,stdout=sys.stderr)

def main():
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify",type=Path); group.add_argument("--clone",type=Path); group.add_argument("--install",type=Path)
    args=parser.parse_args()
    try:
        result=verify(args.verify) if args.verify else clone(args.clone) if args.clone else install(args.install)
    except PiSourceError as exc: print(str(exc),file=sys.stderr); return 1
    print(result); return 0
if __name__=="__main__": raise SystemExit(main())
