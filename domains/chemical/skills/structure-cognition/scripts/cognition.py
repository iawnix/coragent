"""Evidence-bound structural observations; no mechanism or TS verdict."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from rdkit import Chem

from analysis_material import validate_material
from geometry_safety import assess
from material import digest


ROLES = {'unknown', 'reactant', 'product', 'intermediate', 'reactive_complex',
         'optimized_structure', 'ts_candidate'}


def _read(path):
    raw = Path(path).read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('structure cognition input exceeds 32 MiB')
    return json.loads(raw), digest(raw)


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ' must be finite')
    return float(value)


def _context(value, ids):
    if not isinstance(value, dict) or value.get('schema_version') != 'chemical-structure-context/1':
        raise ValueError('chemical-structure-context/1 required')
    allowed = {'schema_version', 'role_hint', 'reaction_center', 'bond_changes',
               'reference_material', 'notes'}
    extra = set(value) - allowed
    if extra:
        raise ValueError('unknown context fields: ' + ', '.join(sorted(extra)))
    role = value.get('role_hint', 'unknown')
    if role not in ROLES:
        raise ValueError('unsupported role_hint')
    center = value.get('reaction_center', [])
    if (not isinstance(center, list) or len(center) > len(ids)
            or any(not isinstance(atom, str) or atom not in ids for atom in center)
            or len(set(center)) != len(center)):
        raise ValueError('reaction_center must contain distinct known atom IDs')
    changes = value.get('bond_changes', [])
    if not isinstance(changes, list) or len(changes) > 256:
        raise ValueError('bond_changes must be a bounded list')
    parsed = []
    seen = set()
    for row in changes:
        if not isinstance(row, dict) or set(row) - {'atoms', 'before', 'after', 'note'}:
            raise ValueError('bond change fields are atoms, before, after and note')
        atoms = row.get('atoms')
        if (not isinstance(atoms, list) or len(atoms) != 2 or atoms[0] == atoms[1]
                or any(not isinstance(atom, str) or atom not in ids for atom in atoms)):
            raise ValueError('bond change requires two distinct known atom IDs')
        pair = tuple(sorted(atoms))
        if pair in seen:
            raise ValueError('bond changes must be unique')
        seen.add(pair)
        before, after = _finite(row.get('before'), 'bond change order'), _finite(row.get('after'), 'bond change order')
        if not 0 <= before <= 3 or not 0 <= after <= 3 or before == after:
            raise ValueError('bond orders must differ and be between 0 and 3')
        note = row.get('note')
        if note is not None and (not isinstance(note, str) or len(note) > 4096):
            raise ValueError('bond change note must be text of at most 4096 characters')
        parsed.append({'atoms': list(atoms), 'before': before, 'after': after, **({'note': note} if note is not None else {})})
    notes = value.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 4096:
        raise ValueError('notes must be text of at most 4096 characters')
    reference = value.get('reference_material')
    if reference is not None and not isinstance(reference, dict):
        raise ValueError('reference_material must be a material object or null')
    return {'role': role, 'center': center, 'changes': parsed, 'reference': reference, 'notes': notes}


def _edges(m):
    if m['mol'] is None:
        return {}, 'not_assessed'
    edges = {}
    for bond in m['mol'].GetBonds():
        pair = tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())))
        edges[pair] = float(bond.GetBondTypeAsDouble())
    return edges, 'supplied_graph'


def _output_edges(m, graph_edges):
    # validate_material returns the RDKit molecule in material atom order.
    return {tuple(sorted((m['ids'][a], m['ids'][b]))): order for (a, b), order in graph_edges.items()}


def _relation(distance, radius_sum):
    normalized = None if radius_sum <= 0 else distance / radius_sum
    if normalized is None:
        return 'not_assessed', None
    if distance < max(.35, .5 * radius_sum):
        return 'collapsed', normalized
    if normalized < .75:
        return 'compressed', normalized
    if normalized <= 1.35:
        return 'normal_like', normalized
    return 'elongated', normalized


def _pair_observation(ids, elements, coordinates, pair, table):
    a, b = (ids.index(pair[0]), ids.index(pair[1])) if isinstance(pair[0], str) else pair
    distance = float(np.linalg.norm(coordinates[a] - coordinates[b]))
    radius_sum = float(table.GetRcovalent(elements[a]) + table.GetRcovalent(elements[b]))
    relation, normalized = _relation(distance, radius_sum)
    return {'atoms': [ids[a], ids[b]], 'distance_angstrom': distance,
            'covalent_radius_sum_angstrom': radius_sum,
            'normalized_distance': normalized, 'relation': relation}


def _fragment_observations(m, coordinates):
    groups = m['value'].get('fragments', {}).get('groups')
    if not groups or len(groups) < 2:
        return {'status': 'not_assessed', 'pairs': []}
    centers = []
    for group in groups:
        indexes = [m['ids'].index(atom) for atom in group]
        centers.append(coordinates[indexes].mean(axis=0))
    pairs = []
    for i in range(len(centers)):
        for j in range(i):
            distance = float(np.linalg.norm(centers[i] - centers[j]))
            pairs.append({'fragments': [j, i], 'centroid_distance_angstrom': distance,
                          'observation': 'widely_separated' if distance > 8.0 else 'nearby'})
    return {'status': 'assessed', 'pairs': pairs}


def _angle_observations(ids, coordinates, center):
    """Report local angles without declaring any angle normal or abnormal."""
    distances = np.linalg.norm(coordinates[:, None] - coordinates[None, :], axis=2)
    rows = []
    for atom in center:
        vertex = ids.index(atom)
        neighbors = [j for j in np.argsort(distances[vertex]) if j != vertex][:5]
        for left_index, left in enumerate(neighbors):
            for right in neighbors[left_index + 1:]:
                first = coordinates[left] - coordinates[vertex]
                second = coordinates[right] - coordinates[vertex]
                denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
                if denominator < 1e-12:
                    rows.append({'atoms': [ids[left], atom, ids[right]], 'angle_degrees': None,
                                 'status': 'undefined_zero_vector'})
                    continue
                cosine = float(np.clip(np.dot(first, second) / denominator, -1., 1.))
                rows.append({'atoms': [ids[left], atom, ids[right]],
                             'angle_degrees': float(np.degrees(np.arccos(cosine))),
                             'status': 'observed_only'})
                if len(rows) >= 256:
                    return rows
    return rows


def _reference(material, reference_value):
    if reference_value is None:
        # A reference is optional context. Its absence limits comparison but
        # does not make a single-structure cognition report incomplete.
        return None, []
    reference = validate_material(reference_value, digest(json.dumps(reference_value, sort_keys=True, separators=(',', ':')).encode()))
    if reference['ids'] != material['ids'] or any(
            (a['element'], a.get('isotope')) != (b['element'], b.get('isotope'))
            for a, b in zip(material['atoms'], reference['atoms'])):
        raise ValueError('reference must have identical atom IDs, order, elements and isotopes')
    if material['coordinates'] is None or reference['coordinates'] is None:
        return {'status': 'not_assessed', 'reference_sha256': reference['sha256']}, ['reference_geometry_missing']
    deltas = []
    for i, atom in enumerate(material['ids']):
        delta = material['coordinates'][i] - reference['coordinates'][i]
        deltas.append({'atom_id': atom, 'displacement_angstrom': float(np.linalg.norm(delta))})
    distances = np.linalg.norm(material['coordinates'][:, None] - material['coordinates'][None, :], axis=2)
    ref_distances = np.linalg.norm(reference['coordinates'][:, None] - reference['coordinates'][None, :], axis=2)
    pair_changes = []
    for i in range(len(material['ids'])):
        for j in range(i):
            pair_changes.append({'atoms': [material['ids'][j], material['ids'][i]],
                                 'distance_delta_angstrom': float(distances[i, j] - ref_distances[i, j])})
    return {'status': 'assessed', 'reference_sha256': reference['sha256'],
            'coordinate_rms_displacement_angstrom': float(np.sqrt(np.mean(np.sum((material['coordinates'] - reference['coordinates']) ** 2, axis=1)))),
            'atom_displacements': deltas, 'pair_distance_deltas': pair_changes}, []


def cognize(material_value, context_value, *, material_sha256=None):
    material = validate_material(material_value, material_sha256 or digest(json.dumps(material_value, sort_keys=True, separators=(',', ':')).encode()))
    context = _context(context_value, material['ids'])
    ids, atoms, coordinates = material['ids'], material['atoms'], material['coordinates']
    elements = [atom['element'] for atom in atoms]
    graph_edges, graph_status = _edges(material)
    graph_edges_by_id = _output_edges(material, graph_edges)
    table = Chem.GetPeriodicTable()
    uncertainties = []
    if material['value'].get('graph') is None:
        uncertainties.append('molecular_graph_not_supplied')
    if coordinates is None:
        uncertainties.append('coordinates_not_supplied')
    if material['value'].get('electronic_state', {}).get('kind') == 'unspecified':
        uncertainties.append('electronic_state_unspecified')
    if not context['center']:
        uncertainties.append('reaction_center_not_declared')
    if context['role'] == 'unknown':
        uncertainties.append('structure_role_not_declared')
    if coordinates is None:
        safety = {'verdict': 'not_assessed', 'reason': 'coordinates_not_supplied'}
        geometry = {'status': 'not_assessed', 'safety': safety}
    else:
        bond_pairs = [tuple(i for i in pair) for pair in graph_edges]
        reaction_pairs = [tuple(ids.index(atom) for atom in row['atoms']) for row in context['changes']]
        safety = assess(elements, coordinates, bonded_pairs=bond_pairs, reaction_pairs=reaction_pairs,
                        profile='ts_candidate' if context['role'] == 'ts_candidate' else 'general')
        geometry = {'status': 'assessed', 'safety': safety,
                    'coordinate_span_angstrom': (coordinates.max(axis=0) - coordinates.min(axis=0)).tolist(),
                    'centroid_angstrom': coordinates.mean(axis=0).tolist(),
                    'fragment_separation': _fragment_observations(material, coordinates),
                    'local_angles': _angle_observations(ids, coordinates, context['center'])}
        if max(geometry['coordinate_span_angstrom'], default=0) > 15:
            uncertainties.append('coordinate_extent_is_large_review_fragment_orientation')
        if safety.get('verdict') == 'unsafe':
            uncertainties.append('geometry_safety_has_hard_failure')
    center_pairs = []
    for row in context['changes']:
        observation = None if coordinates is None else _pair_observation(ids, elements, coordinates, row['atoms'], table)
        item = {**row, 'observation': observation}
        if graph_edges_by_id:
            item['graph_before_order'] = graph_edges_by_id.get(tuple(sorted(row['atoms'])), 0.0)
            if abs(item['graph_before_order'] - row['before']) > 1e-8:
                item['graph_consistency'] = 'before_order_differs_from_graph'
                uncertainties.append('bond_change_graph_mismatch')
            else:
                item['graph_consistency'] = 'before_order_matches_graph'
        else:
            item['graph_consistency'] = 'not_assessed'
        center_pairs.append(item)
    neighbors = []
    if coordinates is not None:
        distances = np.linalg.norm(coordinates[:, None] - coordinates[None, :], axis=2)
        for atom in context['center']:
            index = ids.index(atom)
            order = [j for j in np.argsort(distances[index]) if j != index][:6]
            neighbors.append({'atom_id': atom, 'nearest': [
                {'atom_id': ids[j], 'distance_angstrom': float(distances[index, j])} for j in order]})
    reference, reference_uncertainties = _reference(material, context['reference'])
    uncertainties.extend(reference_uncertainties)
    follow_up = []
    if 'geometry_safety_has_hard_failure' in uncertainties:
        follow_up.append({'skill': 'geometry-safety', 'reason': 'review and repair hard coordinate failures before a solver'})
    if not context['center'] or not context['changes']:
        follow_up.append({'skill': 'mechanism-reasoning', 'reason': 'make the elementary-step and reaction-center hypothesis explicit'})
    if context['role'] in {'ts_candidate', 'reactive_complex'} and coordinates is not None:
        follow_up.append({'skill': 'validation', 'reason': 'geometry alone cannot establish a saddle or TS identity'})
    if context['changes']:
        follow_up.append({'skill': 'reactive-geometry', 'reason': 'use explicit edits only if the hypothesis needs a revised seed'})
    status = 'assessed' if not uncertainties else 'partial'
    if coordinates is None or not ids:
        status = 'inconclusive'
    return {
        'schema_version': 'chemical-structure-cognition/1',
        'status': status,
        'material_sha256': material['sha256'],
        'role_assessment': {'role': context['role'], 'basis': 'declared' if context['role'] != 'unknown' else 'unresolved'},
        'structure_summary': {
            'atom_count': len(ids), 'atom_ids': ids, 'elements': elements,
            'graph_status': graph_status, 'bond_count': len(graph_edges),
            'fragment_count': len(material['value'].get('fragments', {}).get('groups') or []),
            'charge': material['value'].get('charge'), 'multiplicity': material['value'].get('multiplicity'),
            'electronic_state': material['value'].get('electronic_state'),
            'arrangement': material['value'].get('arrangement'),
        },
        'geometry_observations': geometry,
        'reaction_center': {'atom_ids': context['center'], 'neighbors': neighbors,
                            'bond_changes': center_pairs, 'declared_pair_count': len(center_pairs)},
        'comparison': reference,
        'uncertainties': sorted(set(uncertainties)),
        'follow_up': follow_up,
        'notes': context['notes'],
        'scope': 'Structural observations under declared atom identity; no coordinate-derived bond assignment, electronic-state proof, TS certification or mechanism verdict.'
    }
