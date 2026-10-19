"""Generate reaction-center-aware rigid poses for mapped reactant fragments."""
from pathlib import Path
import itertools
import json
import math
import sys

import numpy as np
from rdkit import Chem

SKILLS = Path(__file__).resolve().parents[2]
for part in ("_shared", "material-preparation/scripts/materials", "crest/scripts", "candidate-generation/scripts/path"):
    sys.path.insert(0, str(SKILLS / part))

from analysis_material import read_json
from ensemble_material import canonical, checked, xyz_text
from geometry_safety import COVALENT_RADII, assess
from material import digest, object_fields
from path_contract import candidate_material


def _unit(vector, name):
    value = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(value)
    if norm < 1e-10:
        raise ValueError(f"{name} is degenerate")
    return value / norm


def _rotation(axis, angle):
    axis = _unit(axis, "rotation axis")
    x, y, z = axis
    skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    return np.eye(3) + math.sin(angle) * skew + (1 - math.cos(angle)) * (skew @ skew)


def _align(source, target):
    """Return a proper rotation mapping one vector onto another."""
    source, target = _unit(source, "source direction"), _unit(target, "target direction")
    cross = np.cross(source, target)
    cosine = float(np.clip(source @ target, -1., 1.))
    if np.linalg.norm(cross) < 1e-10:
        if cosine > 0:
            return np.eye(3)
        basis = np.eye(3)[np.argmin(np.abs(source))]
        return _rotation(np.cross(source, basis), math.pi)
    return _rotation(cross, math.acos(cosine))


def _fit(source, target):
    """Fit source points to target points with a proper rigid transform."""
    source, target = np.asarray(source, float), np.asarray(target, float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("rigid fit requires matching N x 3 point arrays")
    left, right = source.mean(axis=0), target.mean(axis=0)
    if len(source) < 2:
        return np.eye(3), left, right
    u, _, vt = np.linalg.svd((source - left).T @ (target - right))
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    return u @ correction @ vt, left, right


def _fragment_data(material):
    fragments = [tuple(int(index) for index in row) for row in Chem.GetMolFrags(material["mol"])]
    if not fragments or sum(map(len, fragments)) != len(material["ids"]):
        raise ValueError("material graph fragments do not cover the atom order")
    owners = {}
    for number, fragment in enumerate(fragments):
        for index in fragment:
            owners[index] = number
    return fragments, owners


def _radius(element):
    return float(COVALENT_RADII.get(element, 1.0))


def _outward(index, coords, mol, fragment):
    neighbors = [neighbor.GetIdx() for neighbor in mol.GetAtomWithIdx(index).GetNeighbors()]
    if neighbors:
        vector = coords[index] - coords[neighbors].mean(axis=0)
    else:
        vector = coords[index] - coords[list(fragment)].mean(axis=0)
    if np.linalg.norm(vector) < 1e-10:
        # A symmetric or isolated atom has no graph-derived face.  Its current
        # fragment axis is still a deterministic, auditable fallback.
        vector = coords[index] - coords.mean(axis=0)
    return _unit(vector, f"atom {index} local direction")


def _directions(base, cone_degrees, count, rng):
    base = _unit(base, "reaction-center direction")
    if count == 1 or cone_degrees == 0:
        return [base]
    helper = np.eye(3)[np.argmin(np.abs(base))]
    first = _unit(np.cross(base, helper), "direction basis")
    second = np.cross(base, first)
    result = [base]
    # One central direction plus a reproducible cone ring.  The random phase
    # explores equivalent faces without making the result nondeterministic.
    phase = float(rng.uniform(0., 2 * math.pi))
    angle = math.radians(cone_degrees)
    for index in range(count - 1):
        theta = phase + 2 * math.pi * index / max(1, count - 1)
        lateral = math.cos(theta) * first + math.sin(theta) * second
        result.append(_unit(math.cos(angle) * base + math.sin(angle) * lateral, "sampled direction"))
    return result


def _validate(spec):
    object_fields(spec, ("schema_version", "material", "bond_changes", "sampling"), "reactive pose input")
    if spec.get("schema_version") != "chemical-reactive-pose/1":
        raise ValueError("chemical-reactive-pose/1 required")
    source = checked(spec.get("material"))
    if source["coordinates"] is None or not 2 <= len(source["ids"]) <= 256:
        raise ValueError("2..256 atoms with angstrom coordinates required")
    if source["mol"] is None:
        raise ValueError("a mapped molecular graph is required")
    fragments, owners = _fragment_data(source)
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
    forming = [row for row in changes if row["before"] == 0 and row["after"] > 0]
    if not forming:
        raise ValueError("at least one interfragment forming bond is required")
    if any(owners[a] == owners[b] for row in forming for a, b in [row["indices"]]):
        raise ValueError("forming bond must connect separate reference fragments")
    sampling = spec.get("sampling", {})
    object_fields(sampling, ("count", "seed", "direction_count", "cone_degrees", "distances", "twists", "pair_tolerance", "clash_scale"), "sampling")
    count = sampling.get("count", 32)
    if type(count) is not int or not 1 <= count <= 256:
        raise ValueError("count must be 1..256")
    seed = sampling.get("seed", 0)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be a uint32")
    direction_count = sampling.get("direction_count", 7)
    if type(direction_count) is not int or not 1 <= direction_count <= 32:
        raise ValueError("direction_count must be 1..32")
    cone = sampling.get("cone_degrees", 35.)
    if type(cone) not in (int, float) or not math.isfinite(cone) or not 0 <= cone <= 90:
        raise ValueError("cone_degrees must be in 0..90")
    distances = sampling.get("distances")
    if distances is None:
        distances = []
        for row in forming:
            a, b = row["indices"]
            base = max(1.6, min(3.2, _radius(source["atoms"][a]["element"]) + _radius(source["atoms"][b]["element"]) + .7))
            distances.append([round(base + offset, 3) for offset in (0., .35, .7)])
    if not isinstance(distances, list) or len(distances) not in (1, len(forming)):
        raise ValueError("distances must apply to all forming pairs or one shared list")
    distance_rows = distances if len(distances) == len(forming) else distances * len(forming)
    if any(not isinstance(row, list) or not 1 <= len(row) <= 16 for row in distance_rows):
        raise ValueError("each distance list must contain 1..16 values")
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 1.0 <= value <= 5.0
           for row in distance_rows for value in row):
        raise ValueError("forming distances must be finite values in 1..5 angstrom")
    twists = sampling.get("twists", [0., 120., -120.])
    if not isinstance(twists, list) or not 1 <= len(twists) <= 16 or any(type(value) not in (int, float) or not math.isfinite(value) or not -180 <= value <= 180 for value in twists):
        raise ValueError("twists must contain 1..16 values in -180..180 degrees")
    pair_tolerance = sampling.get("pair_tolerance", .25)
    if type(pair_tolerance) not in (int, float) or not math.isfinite(pair_tolerance) or not .01 <= pair_tolerance <= 1:
        raise ValueError("pair_tolerance must be in .01..1 angstrom")
    clash_scale = sampling.get("clash_scale", .72)
    if type(clash_scale) not in (int, float) or not math.isfinite(clash_scale) or not .5 <= clash_scale <= 1.5:
        raise ValueError("clash_scale must be in .5..1.5")
    parsed = {"count": count, "seed": seed, "direction_count": direction_count, "cone_degrees": float(cone),
              "distances": [[float(value) for value in row] for row in distance_rows],
              "twists": [float(value) for value in twists], "pair_tolerance": float(pair_tolerance),
              "clash_scale": float(clash_scale)}
    return source, fragments, owners, edges, changes, forming, parsed


def _apply_pose(source, fragments, owners, forming, choices, sampling, rng):
    xyz = source["coordinates"].copy()
    ids, mol = source["ids"], source["mol"]
    transforms = []
    grouped = {}
    for row, direction, distance, twist in zip(forming, choices["directions"], choices["distances"], choices["twists"]):
        a, b = row["indices"]
        fixed_component, mobile_component = (owners[a], owners[b]) if len(fragments[owners[a]]) >= len(fragments[owners[b]]) else (owners[b], owners[a])
        fixed, mobile = (a, b) if fixed_component == owners[a] else (b, a)
        grouped.setdefault(mobile_component, []).append((fixed, mobile, direction, distance, twist, row))
    for component, rows in grouped.items():
        mobile_atoms = np.asarray(fragments[component], dtype=int)
        # The input pair is not an orientation contract.  Each row was
        # normalized above to the actual fixed/mobile roles, so all fitting
        # and residual calculations must use those selected atoms.
        mobile_points = np.asarray([xyz[row[1]] for row in rows])
        targets = np.asarray([xyz[row[0]] + row[2] * row[3] for row in rows])
        if len(rows) == 1:
            fixed, mobile, direction, distance, twist, change = rows[0]
            try:
                mobile_direction = _outward(mobile, xyz, mol, fragments[component])
                rotation = _align(mobile_direction, -direction)
                if twist:
                    rotation = rotation @ _rotation(-direction, math.radians(twist))
            except ValueError:
                rotation = np.eye(3)
            pivot = xyz[mobile].copy()
            xyz[mobile_atoms] = (xyz[mobile_atoms] - pivot) @ rotation.T + pivot
            shift = targets[0] - xyz[mobile]
            xyz[mobile_atoms] += shift
            residual = 0.
            transforms.append({"mobile_fragment": component, "fixed_atom": ids[fixed], "mobile_atom": ids[mobile],
                               "distance": float(distance), "direction": direction.tolist(), "twist_degrees": float(twist),
                               "rotation": rotation.tolist(), "translation": shift.tolist(), "pair_residual": residual})
        else:
            rotation, left, right = _fit(mobile_points, targets)
            moved = (xyz[mobile_atoms] - left) @ rotation + right
            residual = np.linalg.norm(moved[[list(mobile_atoms).index(row[1]) for row in rows]] - targets, axis=1)
            xyz[mobile_atoms] = moved
            transforms.append({"mobile_fragment": component, "pairs": [[ids[row[0]], ids[row[1]]] for row in rows],
                               "rotation": rotation.tolist(), "translation": (right - left @ rotation).tolist(),
                               "pair_residual": float(residual.max())})
    return xyz, transforms


def generate(spec):
    source, fragments, owners, edges, changes, forming, sampling = _validate(spec)
    coords, mol, ids = source["coordinates"], source["mol"], source["ids"]
    rng = np.random.default_rng(sampling["seed"])
    directions = []
    for row in forming:
        a, b = row["indices"]
        fixed, mobile = (a, b) if len(fragments[owners[a]]) >= len(fragments[owners[b]]) else (b, a)
        try:
            base = _outward(fixed, coords, mol, fragments[owners[fixed]])
        except ValueError:
            base = _unit(coords[list(fragments[owners[mobile]])].mean(axis=0) - coords[fixed], "fragment approach")
        directions.append(_directions(base, sampling["cone_degrees"], sampling["direction_count"], rng))
    choices = itertools.product(*directions, *sampling["distances"], sampling["twists"])
    candidates, rejected = [], []
    reaction_pairs = [row["indices"] for row in forming]
    for attempt, selected in enumerate(choices, 1):
        if attempt > sampling["count"]:
            break
        direction_values = selected[:len(forming)]
        offset = len(forming)
        distance_values = selected[offset:offset + len(forming)]
        twist_values = [selected[-1]] * len(forming)
        record = {"id": f"pose-{attempt:04d}", "validated_ts": False, "preoptimization": "not_run",
                  "reaction_pairs": [[ids[a], ids[b]] for a, b in reaction_pairs],
                  "settings": {"directions": [value.tolist() for value in direction_values],
                               "distances": [float(value) for value in distance_values], "twists_degrees": [float(value) for value in twist_values]}}
        try:
            xyz, transforms = _apply_pose(source, fragments, owners, forming,
                                          {"directions": direction_values, "distances": distance_values, "twists": twist_values}, sampling, rng)
            safety = assess([atom["element"] for atom in source["atoms"]], xyz,
                            bonded_pairs=list(edges), reaction_pairs=reaction_pairs,
                            profile="reaction_seed", clash_scale=sampling["clash_scale"])
            report = {"safety": safety, "transforms": transforms,
                      "pair_distances": [float(np.linalg.norm(xyz[a] - xyz[b])) for a, b in reaction_pairs]}
            record.update(coordinates=xyz.tolist(), diagnostics=report)
            if any(item["pair_residual"] > sampling["pair_tolerance"] for item in transforms):
                report["reasons"] = ["multi_pair_rigid_fit_residual"]
            elif safety["verdict"] != "safe":
                report["reasons"] = [row["kind"] for row in safety["hard_failures"]]
            else:
                report["reasons"] = []
            if not report["reasons"]:
                record["material"] = candidate_material(source, xyz, {"operation": "reactive_pose", "input_sha256": canonical(spec),
                                                                      "transforms": transforms, "reaction_pairs": record["reaction_pairs"]})
                candidates.append(record)
            else:
                rejected.append(record)
        except (ValueError, np.linalg.LinAlgError) as exc:
            record.update(coordinates=coords.tolist(), diagnostics={"reasons": [str(exc)]})
            rejected.append(record)
    total_combinations = math.prod(len(group) for group in directions) * math.prod(len(group) for group in sampling["distances"]) * len(sampling["twists"])
    result = {"schema_version": "chemical-reactive-pose-result/1", "input_sha256": canonical(spec),
              "material_sha256": source["sha256"], "reaction_pairs": [[ids[a], ids[b]] for a, b in reaction_pairs],
              "sampling": sampling, "candidates": candidates, "rejected": rejected,
              "summary": {"attempted": len(candidates) + len(rejected), "accepted": len(candidates),
                          "rejected": len(rejected), "enumeration_complete": total_combinations <= sampling["count"]},
              "scope": "Reaction-center-aware rigid fragment poses from explicit mapped bond changes; no conformer energy ranking, mechanism inference or TS validation.",
              "limitations": ["Input coordinates must come from chemical.seed, CREST or supplied geometry; this executor does not embed SMILES.",
                             "Local outward directions are geometry-derived hypotheses, not orbital evidence.",
                             "Accepted poses require solver refinement and TS/IRC validation."]}
    return result


def run(input_path, output_dir):
    spec, source_sha = read_json(input_path)
    result = generate(spec)
    source = checked(spec["material"])
    output = Path(output_dir)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "input.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    for group in ("candidates", "rejected"):
        for row in result[group]:
            folder = output / group / row["id"]
            folder.mkdir(parents=True)
            xyz = xyz_text(source["atoms"], np.asarray(row["coordinates"]), "Reactive pose; validated_ts=false")
            (folder / "geometry.xyz").write_text(xyz)
            if "material" in row:
                (folder / "material.json").write_text(json.dumps(row["material"], ensure_ascii=False, indent=2) + "\n")
            row["xyz"] = {"path": f"{group}/{row['id']}/geometry.xyz", "sha256": digest(xyz.encode())}
    result["input_file_sha256"] = source_sha
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    from pose_cli import parse_arguments
    args = parse_arguments()
    result = run(args.input, args.output_dir)
    raise SystemExit(0 if result["candidates"] else 1)
