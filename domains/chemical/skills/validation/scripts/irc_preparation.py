"""Prepare independent forward and reverse Gaussian IRC inputs.

This module belongs to transition-state validation.  It deliberately has no
dependency on candidate-generation code: the only reaction helper it uses is
the shared explicit atom correspondence checker.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

SKILL_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "_shared").is_dir())
sys.path.insert(0, str(SKILL_ROOT / "_shared"))

from reaction_checks import calculation_spec, molecules, ordered_molecule, reaction
from xyz import validate_electronic_state


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def output_directory(path: Path) -> Path:
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError("output directory must be empty")
    return path


def _validate_explicit_rows(spec: dict, transformation: dict, atom_ids: set[int]) -> None:
    changes = transformation.get("bond_changes")
    if not isinstance(changes, list):
        raise ValueError("explicit transformation requires the complete bond_changes list")
    seen: set[tuple[int, int]] = set()
    for row in changes:
        pair = row.get("atoms") if isinstance(row, dict) else None
        if (not isinstance(pair, list) or len(pair) != 2
                or any(type(n) is not int or n not in atom_ids for n in pair)
                or pair[0] == pair[1]):
            raise ValueError("bond_changes atoms must be two distinct existing map IDs")
        key = tuple(sorted(pair))
        if key in seen:
            raise ValueError("duplicate bond_changes pair")
        seen.add(key)
        if any(type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0
               for key in ("before", "after")):
            raise ValueError("bond_changes before/after must be finite nonnegative bond orders")
    if "hydrogen_changes" not in transformation:
        return
    hydrogen = transformation["hydrogen_changes"]
    if not isinstance(hydrogen, list):
        raise ValueError("hydrogen_changes must be a list")
    seen_h: set[int] = set()
    for row in hydrogen:
        if (not isinstance(row, dict) or type(row.get("atom")) is not int
                or row["atom"] not in atom_ids or row["atom"] in seen_h
                or any(type(row.get(key)) is not int or row[key] < 0 for key in ("before", "after"))):
            raise ValueError("hydrogen_changes requires unique existing atom IDs and nonnegative counts")
        seen_h.add(row["atom"])


def validate_spec(spec: dict) -> tuple[dict, list]:
    """Validate the reaction declaration needed to bind an IRC request."""
    calculation_spec(spec)
    transformation = spec.get("transformation")
    if not isinstance(transformation, dict) or transformation.get("kind") != "explicit":
        raise ValueError("IRC preparation requires kind=explicit with bond_changes")
    sides = molecules(spec.get("mapped_smiles", ""))
    atom_ids = {atom.GetAtomMapNum() for atom in sides[0].GetAtoms()}
    _validate_explicit_rows(spec, transformation, atom_ids)
    checks = reaction(spec["mapped_smiles"], transformation)
    required = ("element_charge_balance", "map_identity", "declared_transformation")
    if any(checks["checks"][key]["verdict"] != "pass" for key in required):
        raise ValueError("mapped reaction does not match its declared transformation")
    if checks["checks"]["atom_hydrogen_changes"]["verdict"] == "fail":
        raise ValueError("mapped reaction does not match declared hydrogen changes")
    ordered = [ordered_molecule(molecule) for molecule in sides]
    if ordered[0][1] != ordered[1][1]:
        raise ValueError("endpoint atom correspondence differs; explicitly map transferred H atoms")
    for molecule, _ in ordered:
        if any(atom.GetIsotope() for atom in molecule.GetAtoms()):
            raise ValueError("isotope-specific masses require an explicit Gaussian input")
        if any(atom.GetFormalCharge() != 0 for atom in molecule.GetAtoms()):
            # Molecular charge is checked below; per-atom charge is valid and
            # must not be rejected for ordinary ionic structures.
            pass
        if sum(atom.GetFormalCharge() for atom in molecule.GetAtoms()) != spec["charge"]:
            raise ValueError("requested charge differs from the molecular graphs")
        validate_electronic_state([(atom.GetSymbol(), 0, 0, 0) for atom in molecule.GetAtoms()],
                                  spec["charge"], spec["multiplicity"])
    return checks, sides


def _header(spec: dict, checkpoint: str, route: str, old: str | None = None) -> str:
    return ((f"%oldchk={old}\n" if old else "")
            + f"%chk={checkpoint}\n%nprocshared={spec['threads']}\n%mem={spec['memory_mb']}MB\n"
            + f"#p {spec['method']}/{spec['basis']} {route}\n\n")


def prepare_irc(spec_file: Path, checkpoint: Path, output: Path, max_points: int = 80) -> dict:
    spec_file = Path(spec_file).resolve()
    spec = json.loads(spec_file.read_text())
    validate_spec(spec)
    checkpoint = Path(checkpoint).resolve()
    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
        raise ValueError("nonempty collected TS checkpoint required")
    if type(max_points) is not int or not 2 <= max_points <= 500:
        raise ValueError("max_points must be between 2 and 500")
    output = output_directory(output)
    shutil.copyfile(checkpoint, output / "ts.chk")
    rows = []
    for direction in ("forward", "reverse"):
        path = output / f"{direction}.gjf"
        route = (f"IRC=({direction.capitalize()},CalcFC,MaxPoints={max_points},StepSize=5) "
                 "Geom=AllCheck Guess=Read SCF=Tight Int=UltraFine NoSymm")
        path.write_text(_header(spec, f"{direction}.chk", route, old="ts.chk") + "\n")
        rows.append({"direction": direction, "path": str(path), "sha256": digest(path)})
    result = {
        "schema_version": "chemical-irc-inputs/1",
        "spec_sha256": digest(spec_file),
        "checkpoint": {"path": str(output / "ts.chk"), "sha256": digest(output / "ts.chk")},
        "inputs": rows,
        "limitations": [
            "Checkpoint bytes are retained, not parsed: verify method, atom order, charge/spin and Hessian against collected TS evidence.",
            "Assess saddle evidence and record unresolved checks before interpreting IRC.",
        ],
    }
    write_json(output / "irc_inputs.json", result)
    return result


def main() -> int:
    from irc_preparation_cli import parse_arguments
    args = parse_arguments()
    result = prepare_irc(args.spec, args.checkpoint, args.output_dir, args.max_points)
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
