"""Optional legacy DA seed strategy; it does not define the general path contract."""
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolTransforms
from path_geometry import align, coordinates


def da_endpoints(spec, reactant, product):
    indexes = {a.GetAtomMapNum(): a.GetIdx() for a in reactant.GetAtoms() if a.GetAtomMapNum()}
    d = [indexes[n] for n in spec['transformation']['diene']]
    rdMolTransforms.SetDihedralDeg(reactant.GetConformer(), *d, 0.0)
    rxyz, pxyz = coordinates(reactant), coordinates(product)
    fragments = Chem.GetMolFrags(reactant)
    for fragment in fragments:
        heavy = [i for i in fragment if reactant.GetAtomWithIdx(i).GetAtomicNum() > 1]
        rotation, left, right = align(rxyz[heavy], pxyz[heavy])
        rxyz[list(fragment)] = (rxyz[list(fragment)]-left) @ rotation+right
    center_a = rxyz[list(fragments[0])].mean(axis=0)
    center_b = rxyz[list(fragments[1])].mean(axis=0)
    axis = center_b-center_a
    if np.linalg.norm(axis) < 1e-8:
        raise ValueError('cannot determine a fragment separation direction')
    axis /= np.linalg.norm(axis)
    # Bound the initial intermolecular contacts; these are seed geometries, not minima.
    cross = [(i, j) for i in fragments[0] for j in fragments[1]]
    for _ in range(50):
        if min(np.linalg.norm(rxyz[j]-rxyz[i]) for i, j in cross) >= 2.0:
            break
        rxyz[list(fragments[0])] -= 0.05*axis
        rxyz[list(fragments[1])] += 0.05*axis
    if min(np.linalg.norm(rxyz[j]-rxyz[i]) for i, j in cross) < 2.0:
        raise ValueError('fragment placement remains overlapping')
    return rxyz, pxyz
