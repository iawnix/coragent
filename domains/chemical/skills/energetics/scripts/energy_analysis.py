"""Finite conformer partitions and balanced, discrete stoichiometric profiles."""
from collections import Counter
import math

from conformers import compare_conformers, state_comparison
from correspondence import mappings
from energy_common import (HARTREE_J_MOL, QUANTITIES, R, UNITS, canonical, composition,
    fields, finite_result, integer, label, material, number, schema)
from thermochemistry import thermochemistry


def compatible(records, quantity):
    first = records[0]
    for record in records:
        if record['quantities'].get(quantity) is None:
            raise ValueError('missing quantity: ' + quantity + '; cannot infer it from electronic energy')
        # Electronic comparisons do not require the same frequency treatment.
        keys = ('electronic',) if quantity == 'E' else ('electronic', 'thermal', 'treatment')
        if any(record['model_signature'][k] != first['model_signature'][k] for k in keys):
            raise ValueError('incompatible energy models/frequency treatments')
        if record['conditions'] != first['conditions']:
            raise ValueError('incompatible temperature, phase or standard states')


def ensemble(spec):
    schema(spec, 'chemical-free-energy-ensemble-input/1', ('members', 'coverage', 'degeneracy_convention'))
    label(spec.get('coverage'), 'coverage')
    if spec.get('degeneracy_convention') != 'additional_unrepresented_basins':
        raise ValueError('degeneracy must count additional unrepresented basins, not rotational symmetry or electronic multiplicity')
    members = spec.get('members')
    if not isinstance(members, list) or not 1 <= len(members) <= 64:
        raise ValueError('ensemble requires 1..64 members')
    records = []; checked = []; ids = set(); weights = []
    for member in members:
        fields(member, ('id', 'thermochemistry', 'degeneracy', 'degeneracy_evidence'), 'ensemble member')
        ident = label(member.get('id'), 'member id')
        if ident in ids: raise ValueError('duplicate member id')
        ids.add(ident)
        weights.append(integer(member.get('degeneracy'), 'degeneracy'))
        label(member.get('degeneracy_evidence'), 'degeneracy_evidence')
        record = thermochemistry(member['thermochemistry'])
        thermal = member['thermochemistry'].get('thermal')
        if thermal is None or thermal['rrho']['stationary_type'] != 'minimum':
            raise ValueError('conformer ensemble requires minima RRHO sources')
        m = material(record['material'])
        for previous in checked:
            if state_comparison(m['value'], previous['value'])['status'] != 'compatible_declarations':
                raise ValueError('ensemble states are incompatible or incomplete')
            identity = mappings(m, previous, mode='identity')
            if identity['status'] != 'candidates':
                raise ValueError('ensemble must contain conformers of the same graph/isotopes/state')
            comparison = compare_conformers(m, previous, rmsd_threshold=.05)
            if comparison['geometry_status'] != 'different':
                raise ValueError('duplicate or unresolved conformer geometry; merge explicitly and account for degeneracy once')
        records.append(record); checked.append(m)
    compatible(records, 'G')
    temperature = records[0]['conditions']['temperature_k']; rt = R * temperature / HARTREE_J_MOL
    energies = [r['quantities']['G'] for r in records]; reference = min(energies)
    logs = [math.log(d) - (g-reference)/rt for d,g in zip(weights,energies)]
    peak = max(logs); partition = math.fsum(math.exp(v-peak) for v in logs)
    logz = peak + math.log(partition)
    populations = [math.exp(v-peak)/partition for v in logs]
    quantities = {q: None for q in QUANTITIES}; quantities['G'] = reference - rt*logz
    return finite_result({'schema_version': 'chemical-free-energy-ensemble-result/1', 'request': spec, 'request_sha256': canonical(spec),
        'unit': 'hartree', 'material': records[0]['material'], 'quantities': quantities,
        'conditions': records[0]['conditions'], 'model_signature': records[0]['model_signature'],
        'members': [{'id': m['id'], 'G_hartree': g, 'degeneracy': d, 'population': p, 'source_request_sha256': r['request_sha256']}
                    for m,g,d,p,r in zip(members, energies, weights, populations, records)],
        'coverage': spec['coverage'], 'scope': 'Equilibrated supplied minima only; no exhaustive sampling, basin-volume integration, kinetic accessibility or independent H/E average is inferred.'})


def energy_record(spec):
    if spec.get('schema_version') == 'chemical-free-energy-ensemble-input/1':
        return ensemble(spec)
    return thermochemistry(spec)


def profile(spec):
    schema(spec, 'chemical-energy-profile-input/1', ('species', 'states', 'reference', 'quantity', 'unit', 'comparisons'))
    quantity = spec.get('quantity'); unit = spec.get('unit')
    if quantity not in ('E', 'E+ZPE', 'H', 'G') or unit not in UNITS:
        raise ValueError('profile needs E, E+ZPE, H or G and hartree, kJ/mol or kcal/mol')
    species = spec.get('species'); states = spec.get('states')
    if not isinstance(species, dict) or not 1 <= len(species) <= 128:
        raise ValueError('profile requires 1..128 named species')
    if not isinstance(states, list) or not 1 <= len(states) <= 256:
        raise ValueError('profile requires 1..256 states')
    records = {label(k, 'species id'): energy_record(v) for k,v in species.items()}
    compatible(list(records.values()), quantity)
    materials = {k: material(r['material']) for k,r in records.items()}
    totals = {}; compositions = {}; charges = {}; spin = {}; used = set()
    for state in states:
        fields(state, ('id', 'stoichiometry'), 'profile state')
        ident = label(state.get('id'), 'state id')
        if ident in totals: raise ValueError('duplicate state id')
        stoich = state.get('stoichiometry')
        if not isinstance(stoich, dict) or not stoich or set(stoich)-set(records):
            raise ValueError('state requires known, explicit stoichiometric participants')
        count = Counter(); charge = 0; terms = []
        for key,n in stoich.items():
            integer(n, 'stoichiometric coefficient', 1000); used.add(key)
            count.update({atom: c*n for atom,c in composition(materials[key]).items()})
            charge += n*materials[key]['value']['charge']
            terms.append(n*records[key]['quantities'][quantity])
        totals[ident] = math.fsum(terms); compositions[ident] = count; charges[ident] = charge
        spin[ident] = {k: {'multiplicity': materials[k]['value']['multiplicity'], 'coefficient': n} for k,n in stoich.items()}
    if used != set(records): raise ValueError('unused species; include spectators/catalysts explicitly in each relevant state')
    reference = spec.get('reference')
    if reference not in totals: raise ValueError('known reference state required')
    if any(compositions[k] != compositions[reference] or charges[k] != charges[reference] for k in totals):
        raise ValueError('profile states are not balanced in atoms/isotopes/charge; check catalysts and spectators')
    rows = [{'id': s['id'], 'stoichiometry': s['stoichiometry'], 'absolute_hartree': totals[s['id']],
             'relative_energy': (totals[s['id']]-totals[reference])*UNITS[unit]} for s in states]
    comparisons = spec.get('comparisons', [])
    if not isinstance(comparisons, list) or len(comparisons) > 256: raise ValueError('bounded comparisons required')
    differences = []
    for pair in comparisons:
        fields(pair, ('from', 'to', 'kind'), 'comparison')
        if pair.get('from') not in totals or pair.get('to') not in totals or pair.get('kind') not in ('reaction', 'activation'):
            raise ValueError('comparison needs known from/to and reaction/activation kind')
        differences.append({**pair, 'energy': (totals[pair['to']]-totals[pair['from']])*UNITS[unit], 'validated_elementary_step': False})
    first = next(iter(records.values()))
    return finite_result({'schema_version': 'chemical-energy-profile-result/1', 'request': spec, 'request_sha256': canonical(spec),
        'quantity': quantity, 'unit': unit, 'reference': reference, 'rows': rows, 'comparisons': differences,
        'conditions': first['conditions'], 'model_signature': first['model_signature'],
        'species_source_sha256': {k: r['request_sha256'] for k,r in records.items()},
        'spin_declarations': spin, 'spin_coupling_and_surface_continuity': 'not_assessed',
        'scope': 'Balanced discrete energy profile, not a complete PES, verified TS connectivity, rate prediction or global optimum.'})


def scan_slice(spec):
    schema(spec, 'chemical-scan-slice-input/1', ('scan', 'unit'))
    scan = spec['scan']; unit = spec.get('unit')
    if unit not in UNITS or scan.get('schema_version') != 'chemical-scan-result/1':
        raise ValueError('scan-slice requires chemical-scan-result/1 and an explicit energy unit')
    axes = scan.get('axes')
    if not isinstance(axes, list) or len(axes) not in (1,2) or scan.get('status') not in ('completed', 'partial', 'failed'):
        raise ValueError('terminal 1D/2D scan required')
    points = scan.get('points')
    if not isinstance(points, list) or not 1 <= len(points) <= 256:
        raise ValueError('bounded scan points required')
    successful = []; excluded = []
    for i,p in enumerate(points):
        if p.get('index') != i or p.get('record_sha256') != canonical({k:v for k,v in p.items() if k != 'record_sha256'}):
            raise ValueError('scan point digest/index mismatch')
        if p.get('status') not in ('succeeded', 'failed', 'pending'):
            raise ValueError('unresolved running scan point')
        if p['status'] != 'succeeded':
            excluded.append({'index': i, 'status': p['status']}); continue
        if not p.get('evidence') or not p.get('primary_sha256'):
            raise ValueError('successful scan point lacks source evidence')
        energy = number(p.get('energy_hartree'), 'scan electronic energy')
        for key in ('targets', 'actual', 'deviations'):
            if not isinstance(p.get(key), list) or len(p[key]) != len(axes):
                raise ValueError('scan coordinate shape mismatch')
            for v in p[key]: number(v, 'scan coordinate')
        for axis,deviation in zip(axes,p['deviations']):
            if not 0 <= deviation <= number(axis.get('tolerance'), 'axis tolerance', True):
                raise ValueError('successful scan point outside tolerance')
        successful.append({'index': i, 'targets': p['targets'], 'actual': p['actual'], 'energy_hartree': energy})
    reference = min((p['energy_hartree'] for p in successful), default=None)
    for p in successful: p['relative_energy'] = (p['energy_hartree'] - reference)*UNITS[unit]
    return finite_result({'schema_version': 'chemical-scan-slice-result/1', 'source_scan_sha256': canonical(scan),
        'quantity': 'E', 'unit': unit, 'axes': axes, 'settings': scan.get('settings'),
        'rows': successful, 'excluded': excluded, 'reference_hartree': reference,
        'scope': 'Finite sampled potential-energy slice; successful points only, no interpolation across failures, path continuity or free-energy sampling.'})
