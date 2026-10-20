"""Separate mapped chemical identity from reference-conformer similarity."""
import numpy as np
from rdkit import Chem

from check_common import check
from conformers import state_comparison
from correspondence import mappings


def geometry_identity(material):
    """Cross-check declared connectivity/stereo against the actual minimum.

    Covalent radii only screen obvious inconsistencies. They do not determine
    bond orders or certify unusual bonding; ambiguous distances need review.
    """
    mol, xyz = material['mol'], material['coordinates']
    if mol is None or xyz is None:
        return check(None, 'Explicit endpoint graph and coordinates required')
    radii = [Chem.GetPeriodicTable().GetRcovalent(a.GetAtomicNum()) for a in mol.GetAtoms()]
    problems, uncertain = [], []
    for i in range(len(xyz)):
        for j in range(i + 1, len(xyz)):
            bonded = mol.GetBondBetweenAtoms(i, j) is not None
            ratio = float(np.linalg.norm(xyz[i] - xyz[j]) / (radii[i] + radii[j]))
            row = {'atoms': [material['ids'][i], material['ids'][j]], 'declared_bond': bonded,
                   'distance_angstrom': float(np.linalg.norm(xyz[i] - xyz[j])), 'covalent_radius_ratio': ratio}
            if ratio < .55 or bonded and ratio > 1.6 or not bonded and ratio < 1.05:
                problems.append(row)
            elif bonded and ratio > 1.35 or not bonded and ratio < 1.25:
                uncertain.append(row)
    expected, observed = Chem.Mol(mol), Chem.Mol(mol)
    conf = Chem.Conformer(len(xyz))
    for i, point in enumerate(xyz): conf.SetAtomPosition(i, point)
    observed.RemoveAllConformers(); observed.AddConformer(conf)
    Chem.AssignStereochemistry(expected, cleanIt=True, force=True)
    Chem.AssignStereochemistryFrom3D(observed, replaceExistingTags=True)
    Chem.AssignStereochemistry(observed, cleanIt=True, force=True)
    stereo = []
    for a, b in zip(expected.GetAtoms(), observed.GetAtoms()):
        if a.HasProp('_CIPCode') and (not b.HasProp('_CIPCode') or a.GetProp('_CIPCode') != b.GetProp('_CIPCode')):
            stereo.append(material['ids'][a.GetIdx()])
    for a, b in zip(expected.GetBonds(), observed.GetBonds()):
        if a.GetStereo() in (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ) and a.GetStereo() != b.GetStereo():
            stereo.append([material['ids'][a.GetBeginAtomIdx()], material['ids'][a.GetEndAtomIdx()]])
    unspecified = any(s.specified == Chem.StereoSpecified.Unspecified for s in Chem.FindPotentialStereo(expected))
    return check(False if problems or stereo else None if uncertain or unspecified else True,
                 {'inconsistent_pairs': problems, 'ambiguous_pairs': uncertain, 'stereo_mismatches': stereo,
                  'unspecified_stereo': unspecified,
                  'scope': 'Geometry screens declared connectivity and specified stereo; bond orders remain attributed graph evidence'})


def compare_identity(endpoint, target, *, max_search, max_candidates):
    correspondence = mappings(endpoint, target, mode='identity', max_search=max_search, max_candidates=max_candidates)
    state = state_comparison(endpoint['value'], target['value'])
    incompatible = correspondence['status'] == 'incompatible' or bool(state['conflicts'])
    # One valid graph correspondence proves identity compatibility; enumeration
    # need not exhaust equivalent H permutations. No candidate is not a match.
    matched = bool(correspondence['candidates']) and state['status'] == 'compatible_declarations'
    return {'status': 'mismatch' if incompatible else 'match' if matched else 'inconclusive',
            'correspondence': correspondence, 'state_comparison': state}
