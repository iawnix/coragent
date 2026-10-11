"""Bounded graph correspondences, with ambiguity and coverage kept explicit."""
from collections import Counter

from rdkit import Chem

from analysis_material import make_order


def edges(mol):
    return {tuple(sorted((b.GetBeginAtomIdx(), b.GetEndAtomIdx()))): b.GetBondTypeAsDouble() for b in mol.GetBonds()}


def graph_identity(mol):
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(copy, canonical=True, isomericSmiles=True)


def stereo_corresponds(left, right, mapping):
    # Unique temporary isotope tags constrain RDKit's stereochemical match to
    # this exact permutation; original isotope compatibility is checked first.
    a, b = Chem.Mol(left), Chem.Mol(right)
    for i, j in enumerate(mapping):
        a.GetAtomWithIdx(i).SetIsotope(1000 + i)
        b.GetAtomWithIdx(j).SetIsotope(1000 + i)
    return b.HasSubstructMatch(a, useChirality=True)


def mappings(left, right, *, mode='reaction', fixed_pairs=(), max_candidates=64, max_search=20000):
    if mode not in {'identity', 'reaction'}:
        raise ValueError('mapping mode must be identity or reaction')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 256 or type(max_search) is not int or not 1 <= max_search <= 1000000:
        raise ValueError('max_candidates must be 1..256 and max_search 1..1000000')
    fixed = {}
    if not isinstance(fixed_pairs, (tuple, list)):
        raise ValueError('fixed_pairs requires pairs of local atom IDs')
    for pair in fixed_pairs:
        if (not isinstance(pair, list) or len(pair) != 2 or pair[0] not in left['ids'] or pair[1] not in right['ids']):
            raise ValueError('fixed_pairs requires existing left/right atom IDs')
        i, j = left['ids'].index(pair[0]), right['ids'].index(pair[1])
        if i in fixed or j in fixed.values():
            raise ValueError('fixed_pairs must be one-to-one without duplicates')
        fixed[i] = j
    result = {'schema_version': 'chemical-correspondence/1', 'mode': mode,
              'sources': {side: s['sha256'] for side, s in [('left', left), ('right', right)]},
              'candidates': [], 'status': 'not_assessed', 'search_complete': False,
              'candidate_limit_reached': False, 'visited': 0, 'max_search': max_search,
              'scope': 'Graph/element/isotope correspondences; not mechanism, electronic-state or atom-trajectory proof'}
    a, b = left['mol'], right['mol']
    if a is None or b is None:
        return {**result, 'reason': 'explicit_graphs_required; XYZ bond inference is not performed'}
    n = a.GetNumAtoms()
    if max(n, b.GetNumAtoms()) > 256:
        return {**result, 'reason': 'bounded_mapper_supports_at_most_256_atoms_per_material'}
    signature = lambda mol: Counter((atom.GetAtomicNum(), atom.GetIsotope()) for atom in mol.GetAtoms())
    if signature(a) != signature(b) or Chem.GetFormalCharge(a) != Chem.GetFormalCharge(b):
        return {**result, 'status': 'incompatible', 'search_complete': True, 'reason': 'declared_composition_isotope_or_total_charge_differs'}
    if mode == 'identity' and graph_identity(a) != graph_identity(b):
        return {**result, 'status': 'incompatible', 'search_complete': True, 'reason': 'molecular_graph_or_specified_stereochemistry_differs'}
    ae, be = edges(a), edges(b)
    amap = {atom.GetAtomMapNum(): atom.GetIdx() for atom in a.GetAtoms() if atom.GetAtomMapNum()}
    bmap = {atom.GetAtomMapNum(): atom.GetIdx() for atom in b.GetAtoms() if atom.GetAtomMapNum()}
    for label in amap.keys() & bmap.keys():
        i, j = amap[label], bmap[label]
        if i in fixed and fixed[i] != j or j in fixed.values() and fixed.get(i) != j:
            raise ValueError('fixed_pairs conflicts with supplied atom-map labels')
        fixed[i] = j
    domains = {}
    for atom in a.GetAtoms():
        i = atom.GetIdx()
        domains[i] = []
        for other in b.GetAtoms():
            j = other.GetIdx()
            if i in fixed and fixed[i] != j or j in fixed.values() and fixed.get(i) != j:
                continue
            if (atom.GetAtomicNum(), atom.GetIsotope()) != (other.GetAtomicNum(), other.GetIsotope()):
                continue
            if atom.GetAtomMapNum() and other.GetAtomMapNum() and atom.GetAtomMapNum() != other.GetAtomMapNum():
                continue
            if mode == 'identity' and (atom.GetFormalCharge(), atom.GetNumRadicalElectrons(), atom.GetDegree()) != (other.GetFormalCharge(), other.GetNumRadicalElectrons(), other.GetDegree()):
                continue
            domains[i].append(j)
    sequence = sorted(range(n), key=lambda i: (len(domains[i]), -a.GetAtomWithIdx(i).GetDegree(), i))
    assigned, used, best, candidates = {}, set(), None, []
    best_count, exhausted, visited = 0, False, 0

    def walk(depth, cost):
        nonlocal best, best_count, exhausted, visited, candidates
        if depth == n:
            mapping = [assigned[i] for i in range(n)]
            if mode == 'identity' and not stereo_corresponds(a, b, mapping):
                return
            if best is None or cost < best:
                best, candidates, best_count = cost, [], 0
            if cost == best:
                best_count += 1
                if len(candidates) < max_candidates:
                    candidates.append(mapping)
            return
        i = sequence[depth]
        for j in domains[i]:
            if j in used:
                continue
            if visited >= max_search:
                exhausted = True
                return
            visited += 1
            differences = [abs(ae.get(tuple(sorted((i, k))), 0.) - be.get(tuple(sorted((j, v))), 0.)) for k, v in assigned.items()]
            if mode == 'identity' and any(differences):
                continue
            score = cost + sum(differences)
            if best is not None and score > best:
                continue
            assigned[i] = j
            used.add(j)
            walk(depth + 1, score)
            used.remove(j)
            del assigned[i]
            if exhausted:
                return

    walk(0, 0.)
    for mapping in candidates:
        changes = []
        for i in range(n):
            for k in range(i + 1, n):
                before = ae.get((i, k), 0.)
                after = be.get(tuple(sorted((mapping[i], mapping[k]))), 0.)
                if before != after:
                    changes.append({'left_atoms': [left['ids'][i], left['ids'][k]], 'before': before, 'after': after})
        result['candidates'].append({'left_to_right': mapping,
            'pairs': [[left['ids'][i], right['ids'][j]] for i, j in enumerate(mapping)],
            'bond_order_edit_cost': best, 'bond_changes': changes,
            'right_order': make_order(right['ids'], mapping)})
    result.update(status='candidates' if candidates else 'inconclusive' if exhausted else 'incompatible',
                  search_complete=not exhausted, candidate_limit_reached=best_count > max_candidates,
                  visited=visited, best_cost=best, best_count_observed=best_count,
                  ambiguity='multiple' if best_count > 1 else 'unknown' if exhausted else 'unique' if best_count == 1 else 'none',
                  ranking='minimum total absolute bond-order edits among explored correspondences; not a reaction likelihood',
                  reason='search_budget_reached' if exhausted else 'search_finished')
    return result
