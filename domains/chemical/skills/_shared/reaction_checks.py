"""Scoped checks for explicit reaction correspondences; no mechanistic inference."""
from collections import Counter
import re

from rdkit import Chem


def molecules(smiles):
    if not isinstance(smiles, str):
        raise ValueError('use a mapped reactants>>products SMILES string')
    parts = smiles.split('>>')
    if len(parts) != 2:
        raise ValueError('use reactants>>products with explicit atom-map numbers')
    parser = Chem.SmilesParserParams()
    parser.removeHs = False  # Explicit mapped H atoms must retain their identity across a transfer.
    sides = [Chem.MolFromSmiles(part, parser) for part in parts]
    if any(mol is None or mol.GetNumAtoms() == 0 for mol in sides):
        raise ValueError('invalid reaction SMILES')
    for mol in sides:
        ids = [a.GetAtomMapNum() for a in mol.GetAtoms()]
        if any(n <= 0 for n in ids) or len(ids) != len(set(ids)):
            raise ValueError('every explicit atom needs a unique positive map number on each side')
    return sides


def bonds(mol):
    return {tuple(sorted((b.GetBeginAtom().GetAtomMapNum(), b.GetEndAtom().GetAtomMapNum()))):
            b.GetBondTypeAsDouble() for b in mol.GetBonds()}


def ordered_molecule(mol):
    """Stable heavy/explicit atom map order, then H by parent map and local ordinal."""
    full = Chem.AddHs(mol)
    keys = []
    counters = Counter()
    for atom in full.GetAtoms():
        if atom.GetAtomMapNum():
            key = (0, atom.GetAtomMapNum(), 0)
        else:
            if atom.GetAtomicNum() != 1 or atom.GetDegree() != 1:
                raise ValueError('only added hydrogen atoms may lack map numbers')
            parent = atom.GetNeighbors()[0].GetAtomMapNum()
            counters[parent] += 1
            key = (1, parent, counters[parent])
        keys.append(key)
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    return Chem.RenumberAtoms(full, order), [list(keys[i]) for i in order]


def reaction(smiles, transformation=None):
    sides = molecules(smiles)
    inventories = [Counter((a.GetSymbol(), a.GetIsotope()) for a in Chem.AddHs(m).GetAtoms()) for m in sides]
    charges = [Chem.GetFormalCharge(m) for m in sides]
    identities = [{a.GetAtomMapNum(): (a.GetSymbol(), a.GetIsotope()) for a in m.GetAtoms()} for m in sides]
    hydrogens = [{a.GetAtomMapNum(): a.GetTotalNumHs(includeNeighbors=True) for a in m.GetAtoms()} for m in sides]
    edges = [bonds(m) for m in sides]
    changes = [{'atoms': list(p), 'before': edges[0].get(p, 0.), 'after': edges[1].get(p, 0.)}
               for p in sorted(set(edges[0]) | set(edges[1])) if edges[0].get(p) != edges[1].get(p)]
    hchanges = [{'atom': n, 'before': hydrogens[0].get(n), 'after': hydrogens[1].get(n)}
                for n in sorted(set(hydrogens[0]) | set(hydrogens[1])) if hydrogens[0].get(n) != hydrogens[1].get(n)]
    mapped = identities[0] == identities[1]
    balanced = inventories[0] == inventories[1] and charges[0] == charges[1]
    checks = {'molecular_graphs': {'verdict': 'pass'},
              'element_charge_balance': {'verdict': 'pass' if balanced else 'fail'},
              'map_identity': {'verdict': 'pass' if mapped else 'fail'},
              'atom_hydrogen_changes': {'verdict': 'not_assessed', 'changes': hchanges},
              'declared_transformation': {'verdict': 'not_assessed'},
              'stereochemical_correspondence': {'verdict': 'not_assessed'}}
    if transformation is not None:
        kind = transformation.get('kind')
        if kind == 'explicit':
            expected = transformation.get('bond_changes')
            if not isinstance(expected, list):
                raise ValueError('explicit transformation requires bond_changes')
            canonical = lambda rows: sorted((tuple(sorted(r['atoms'])), r['before'], r['after']) for r in rows)
            checks['declared_transformation'] = {'verdict': 'pass' if mapped and balanced and canonical(changes) == canonical(expected) else 'fail', 'kind': kind}
            expected_h = transformation.get('hydrogen_changes')
            if expected_h is not None:
                checks['atom_hydrogen_changes']['verdict'] = 'pass' if sorted(hchanges, key=lambda r:r['atom']) == sorted(expected_h, key=lambda r:r['atom']) else 'fail'
        else:
            raise ValueError('transformation requires kind=explicit with bond_changes')
    return {'schema_version': 'chemical-reaction/2', 'balanced': balanced, 'mapping_valid': mapped,
            'charges': charges, 'bond_changes': changes, 'hydrogen_changes': hchanges, 'checks': checks,
            'limitations': ['Graph checks do not establish a transition state, IRC connection, or stereochemical mechanism.',
                            'Implicit hydrogen correspondence is counted per mapped atom; individual H transfer needs explicit H maps.']}


def calculation_spec(value):
    """Common path schema and Gaussian settings, without a reaction topology rule."""
    if not isinstance(value, dict) or value.get('schema_version') != 'chemical-path-spec/1':
        raise ValueError('chemical-path-spec/1 required')
    for key in ('method', 'basis'):
        if not isinstance(value.get(key), str) or not re.fullmatch(r'[A-Za-z0-9+*(),._-]+', value[key]):
            raise ValueError('method/basis must be explicit Gaussian route tokens')
    for key in ('charge', 'multiplicity', 'threads', 'memory_mb'):
        if type(value.get(key)) is not int or key != 'charge' and value[key] < 1:
            raise ValueError('explicit charge, multiplicity, threads and memory_mb required')
