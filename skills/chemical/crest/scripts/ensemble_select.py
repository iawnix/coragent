"""Conservative bounded leader clustering, preserving every selection decision."""
import math

from conformers import compare_conformers, state_comparison
from correspondence import graph_identity
from crest_io import HARTREE_TO_KCAL
from ensemble_material import canonical, checked, identity_check


def select_ensemble(ensemble, *, energy_window=6., rmsd=.1, max_selected=32, max_pairs=1024,
                    max_candidates=64, max_search=20000):
    if not isinstance(ensemble, dict) or ensemble.get('schema_version') != 'chemical-ensemble/1':
        raise ValueError('chemical-ensemble/1 required')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (energy_window, rmsd)):
        raise ValueError('energy window and RMSD must be finite positive values')
    if type(max_selected) is not int or not 1 <= max_selected <= 256 or type(max_pairs) is not int or not 1 <= max_pairs <= 100000:
        raise ValueError('max-selected must be 1..256 and max-pairs 1..100000')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 256 or type(max_search) is not int or not 1 <= max_search <= 1000000:
        raise ValueError('max-candidates must be 1..256 and max-search 1..1000000')
    members = ensemble.get('members')
    if not isinstance(members, list) or not 1 <= len(members) <= 1024: raise ValueError('1..1024 ensemble members required')
    if any(not isinstance(m, dict) for m in members): raise ValueError('member objects required')
    ids = [m.get('id') for m in members]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids): raise ValueError('unique member IDs required')
    source = checked(ensemble['reference_material'])
    rows = []; models = set()
    for m in members:
        row = {'id': m['id'], 'decision': 'unresolved', 'energy_hartree': None, 'relative_kcal_mol': None}
        if m.get('material') is None:
            row.update(decision='unusable', reason='missing_material'); rows.append(row); continue
        material = checked(m['material'])
        if material['coordinates'] is None:
            row.update(decision='unusable', reason='missing_coordinates'); rows.append(row); continue
        row['material'] = material
        identity = identity_check(material)
        row['identity'] = identity
        state = state_comparison(source['value'], material['value'])
        row['state_comparison'] = state
        same_atoms = material['ids'] == source['ids'] and [(a['element'], a.get('isotope')) for a in material['atoms']] == [(a['element'], a.get('isotope')) for a in source['atoms']]
        same_graph = None if source['mol'] is None or material['mol'] is None else graph_identity(source['mol']) == graph_identity(material['mol'])
        row['same_reference_graph'] = same_graph
        if not same_atoms or same_graph is False or identity['status'] == 'different' or state['conflicts']:
            row.update(decision='excluded', reason='identity_or_declared_state_differs'); rows.append(row); continue
        energy = m.get('energy')
        if energy is not None:
            if (not isinstance(energy, dict) or energy.get('unit') != 'hartree' or type(energy.get('value')) not in (int, float)
                    or not math.isfinite(energy['value']) or not isinstance(energy.get('model'), dict)):
                raise ValueError('energy requires finite hartree value and explicit model')
            model = energy['model']
            required = {'method', 'quantity', 'charge', 'multiplicity', 'solvent_model', 'solvent', 'constraints'}
            if not required <= model.keys() or model['quantity'] != 'electronic_energy' or not isinstance(model['method'], str) or not model['method'].strip():
                raise ValueError('complete electronic-energy model required; free energies are a separate analysis')
            if (not isinstance(model['solvent_model'], str) or not model['solvent_model'].strip()
                    or not isinstance(model['constraints'], list)
                    or (model['solvent_model'] == 'gas' and model['solvent'] is not None)
                    or (model['solvent_model'] != 'gas' and (not isinstance(model['solvent'], str) or not model['solvent'].strip()))):
                raise ValueError('explicit solvent and constraint declarations required for energy comparison')
            if model['charge'] != material['value']['charge'] or model['multiplicity'] != material['value']['multiplicity']:
                raise ValueError('energy state and material disagree')
            row['energy_hartree'] = energy['value']; models.add(canonical(model))
        rows.append(row)
    # Never rank energies from different methods, solvent models or constraints.
    comparable = len(models) == 1
    ranked = [r for r in rows if r['decision'] == 'unresolved' and r['energy_hartree'] is not None
              and r['same_reference_graph'] is True and r['identity']['status'] == 'match' and r['state_comparison']['status'] == 'compatible_declarations']
    minimum = min((r['energy_hartree'] for r in ranked), default=None) if comparable else None
    if minimum is not None:
        for row in ranked:
            row['relative_kcal_mol'] = (row['energy_hartree'] - minimum) * HARTREE_TO_KCAL
            if row['relative_kcal_mol'] > energy_window:
                row.update(decision='outside_energy_window', reason='within_one_electronic_energy_model_only')
    pending = [r for r in rows if r['decision'] == 'unresolved']
    if minimum is not None: pending.sort(key=lambda r: (r['relative_kcal_mol'] is None, r['relative_kcal_mol'] or 0))
    leaders = []; comparisons = []; pair_count = 0; pair_exhausted = False; selection_limited = False
    for row in pending:
        uncertain = row['same_reference_graph'] is not True or row['identity']['status'] != 'match' or row['state_comparison']['status'] != 'compatible_declarations'
        duplicate = None
        for leader in leaders:
            if pair_count >= max_pairs:
                pair_exhausted = True; uncertain = True; break
            pair_count += 1
            comp = compare_conformers(row['material'], leader['material'], rmsd_threshold=rmsd,
                                      max_candidates=max_candidates, max_search=max_search)
            comparisons.append({'left': row['id'], 'right': leader['id'], 'geometry_status': comp['geometry_status'],
                                'state_status': comp['state_comparison']['status'], 'coverage_complete': comp.get('coverage_complete'),
                                'rmsd_angstrom': comp['best']['rmsd_angstrom'] if comp.get('best') else None})
            if not uncertain and leader['identity']['status'] == 'match' and comp['geometry_status'] == 'match' and comp['state_comparison']['status'] == 'compatible_declarations':
                duplicate = leader['id']; break
            if comp['geometry_status'] in ('inconclusive', 'not_assessed'): uncertain = True
        if duplicate:
            row.update(decision='duplicate', representative=duplicate)
        elif len(leaders) >= max_selected:
            row.update(decision='deferred', reason='max_selected'); selection_limited = True
        else:
            row.update(decision='selected', reason='unresolved_comparison_retained' if uncertain else 'cluster_representative',
                       needs_identity_review=uncertain)
            leaders.append(row)
    selected = [r['id'] for r in leaders]
    decisions = [{k: v for k, v in r.items() if k != 'material'} for r in rows]
    return {'schema_version': 'chemical-ensemble-selection/1', 'selected_ids': selected, 'decisions': decisions,
            'comparisons': comparisons, 'pair_count': pair_count, 'comparison_budget_exhausted': pair_exhausted, 'selection_limit_reached': selection_limited,
            'energy_ranking': 'comparable' if minimum is not None else 'unranked_missing_or_mixed_models',
            'complete_source': ensemble.get('complete') is True,
            'settings': {'energy_window_kcal_mol': energy_window, 'rmsd_angstrom': rmsd, 'max_selected': max_selected,
                         'max_pairs': max_pairs, 'max_candidates': max_candidates, 'max_search': max_search},
            'scope': 'Greedy leader clustering of sampled geometries and optional electronic-energy screening; unranked members retained, no population/free-energy or global-minimum claim'}
