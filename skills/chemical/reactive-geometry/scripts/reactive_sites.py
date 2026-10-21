"""Analyze mapped reaction centers and emit pose hypotheses for an Agent."""
from pathlib import Path
import json
import math
import sys

import numpy as np
from rdkit import Chem

SKILLS = Path(__file__).resolve().parents[2]
for part in ("_shared", "material-preparation/scripts/materials", "crest/scripts"):
    sys.path.insert(0, str(SKILLS / part))

from analysis_material import read_json  # noqa: E402
from ensemble_material import canonical, checked  # noqa: E402
from geometry_safety import COVALENT_RADII  # noqa: E402
from material import object_fields  # noqa: E402


FAMILIES = {"generic", "sn2", "addition", "elimination", "proton_transfer"}


def _unit(value, name):
    vector = np.asarray(value, dtype=float)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-10:
        raise ValueError(f"{name} is degenerate")
    return vector / norm


def _fragment_data(mol, count):
    fragments = [tuple(int(index) for index in row) for row in Chem.GetMolFrags(mol)]
    if not fragments or sum(map(len, fragments)) != count:
        raise ValueError("material graph fragments do not cover the atom order")
    owners = {index: number for number, row in enumerate(fragments) for index in row}
    return fragments, owners


def _outward(index, coords, mol, fragment):
    neighbors = [neighbor.GetIdx() for neighbor in mol.GetAtomWithIdx(index).GetNeighbors()]
    if neighbors:
        vector = coords[index] - coords[neighbors].mean(axis=0)
    else:
        vector = coords[index] - coords[list(fragment)].mean(axis=0)
    if np.linalg.norm(vector) < 1e-10:
        vector = coords[index] - coords.mean(axis=0)
    return _unit(vector, f"atom {index} local direction")


def _validate(spec):
    object_fields(spec, ("schema_version", "material", "bond_changes", "reaction_family", "max_sites"),
                  "reactive sites input")
    if spec.get("schema_version") != "chemical-reactive-sites/1":
        raise ValueError("chemical-reactive-sites/1 required")
    source = checked(spec.get("material"))
    if source["coordinates"] is None or not 2 <= len(source["ids"]) <= 256:
        raise ValueError("2..256 atoms with angstrom coordinates required")
    if source["mol"] is None:
        raise ValueError("a mapped molecular graph is required")
    fragments, owners = _fragment_data(source["mol"], len(source["ids"]))
    ids, coords, mol = source["ids"], source["coordinates"], source["mol"]
    edges = {tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))): bond.GetBondTypeAsDouble()
             for bond in mol.GetBonds()}
    changes = []
    for row in spec.get("bond_changes", []):
        object_fields(row, ("atoms", "before", "after"), "bond change")
        pair_ids = row.get("atoms")
        if (not isinstance(pair_ids, list) or len(pair_ids) != 2 or pair_ids[0] == pair_ids[1]
                or any(value not in ids for value in pair_ids)):
            raise ValueError("bond change atoms must be two distinct known IDs")
        if any(type(row.get(key)) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0
               for key in ("before", "after")) or row["before"] == row["after"]:
            raise ValueError("bond change orders must be finite, nonnegative and different")
        pair = tuple(sorted(ids.index(value) for value in pair_ids))
        if row["before"] != edges.get(pair, 0):
            raise ValueError("bond change before order differs from the reference graph")
        changes.append({"ids": pair_ids, "indices": pair, "before": row["before"], "after": row["after"]})
    if not changes:
        raise ValueError("at least one bond change is required")
    family = spec.get("reaction_family", "generic")
    if family not in FAMILIES:
        raise ValueError("unsupported reaction_family")
    max_sites = spec.get("max_sites", 64)
    if type(max_sites) is not int or not 1 <= max_sites <= 256:
        raise ValueError("max_sites must be 1..256")
    return source, fragments, owners, coords, changes, family, max_sites


def _distance_hint(source, a, b):
    radius_a = float(COVALENT_RADII.get(source["atoms"][a]["element"], 1.0))
    radius_b = float(COVALENT_RADII.get(source["atoms"][b]["element"], 1.0))
    return round(max(1.6, min(3.2, radius_a + radius_b + 0.7)), 3)


def generate(spec):
    source, fragments, owners, coords, changes, family, max_sites = _validate(spec)
    ids, mol = source["ids"], source["mol"]
    forming = [row for row in changes if row["before"] == 0 and row["after"] > 0]
    breaking = [row for row in changes if row["before"] > 0 and row["after"] == 0]
    sites = []
    for forming_row in forming:
        a, b = forming_row["indices"]
        fixed_component, mobile_component = ((owners[a], owners[b]) if len(fragments[owners[a]]) >= len(fragments[owners[b]])
                                             else (owners[b], owners[a]))
        fixed, mobile = (a, b) if fixed_component == owners[a] else (b, a)
        fixed_breaks = [row for row in breaking if fixed in row["indices"]]
        try:
            base = _outward(fixed, coords, mol, fragments[fixed_component])
            mobile_base = _outward(mobile, coords, mol, fragments[mobile_component])
        except ValueError:
            base = _unit(coords[list(fragments[mobile_component])].mean(axis=0) - coords[fixed],
                         "fragment approach")
            mobile_base = -base
        direction_source = "fixed_local_outward"
        direction = base
        if family == "sn2" and fixed_breaks:
            leaving = fixed_breaks[0]["indices"][0] if fixed_breaks[0]["indices"][1] == fixed else fixed_breaks[0]["indices"][1]
            direction = _unit(coords[fixed] - coords[leaving], "SN2 leaving-group direction")
            direction_source = "opposite_broken_bond"
        hypotheses = [{
            "id": "primary",
            "family": family,
            "direction": direction.tolist(),
            "direction_source": direction_source,
            "distance_angstrom": _distance_hint(source, fixed, mobile),
            "cone_degrees": {"sn2": 20, "addition": 35, "elimination": 25,
                              "proton_transfer": 30}.get(family, 45),
        }, {
            "id": "opposite_face",
            "family": family,
            "direction": (-direction).tolist(),
            "direction_source": "opposite_face_alternative",
            "distance_angstrom": _distance_hint(source, fixed, mobile),
            "cone_degrees": 35,
        }]
        sites.append({
            "id": f"site-{len(sites) + 1:04d}",
            "reaction_center": {
                "forming_pair": [ids[a], ids[b]],
                "breaking_pairs": [[ids[row["indices"][0]], ids[row["indices"][1]]] for row in fixed_breaks],
            },
            "fragment_roles": {
                "fixed_fragment": fixed_component,
                "mobile_fragment": mobile_component,
                "fixed_atom": ids[fixed],
                "mobile_atom": ids[mobile],
            },
            "local_frames": {
                "fixed_outward": base.tolist(),
                "mobile_outward": mobile_base.tolist(),
            },
            "hypotheses": hypotheses,
            "evidence": {
                "reference_material_sha256": source["sha256"],
                "fixed_fragment_size": len(fragments[fixed_component]),
                "mobile_fragment_size": len(fragments[mobile_component]),
                "reaction_family_source": "user_or_agent_declared",
            },
        })
    if len(sites) > max_sites:
        sites = sites[:max_sites]
    return {
        "schema_version": "chemical-reactive-sites-result/1",
        "input_sha256": canonical(spec),
        "material_sha256": source["sha256"],
        "reaction_family": family,
        "sites": sites,
        "summary": {"forming_changes": len(forming), "breaking_changes": len(breaking),
                     "sites": len(sites), "truncated": len(sites) < len(forming)},
        "scope": "Mapped reaction-center and local approach hypotheses; no mechanism, energy, conformer ranking or TS validation.",
        "limitations": [
            "The executor analyzes explicit bond changes; it does not infer a product or reaction family from names.",
            "Local vectors are geometry-derived starting hypotheses, not orbital evidence.",
            "Use chemical.reactive-pose to sample the returned alternatives and retain multiple hypotheses when evidence is ambiguous.",
        ],
    }


def run(input_path, output_dir):
    spec, source_sha = read_json(input_path)
    result = generate(spec)
    output = Path(output_dir)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "input.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    result["input_file_sha256"] = source_sha
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    from reactive_sites_cli import parse_arguments
    args = parse_arguments()
    result = run(args.input, args.output_dir)
    raise SystemExit(0 if result["sites"] else 1)
