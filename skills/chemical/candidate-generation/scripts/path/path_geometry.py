"""Reaction-independent embedding and rigid alignment of endpoint geometries."""
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem


def embed(mol, seed):
    result = Chem.Mol(mol)
    parameters = AllChem.ETKDGv3(); parameters.randomSeed = seed
    if AllChem.EmbedMolecule(result, parameters) != 0:
        raise ValueError('RDKit failed to embed this candidate branch')
    if AllChem.UFFHasAllMoleculeParams(result):
        AllChem.UFFOptimizeMolecule(result, maxIters=300)
    return result


def align(source, target):
    left, right = source.mean(axis=0), target.mean(axis=0)
    u, _, vt = np.linalg.svd((source-left).T @ (target-right))
    correction = np.eye(3); correction[-1, -1] = np.linalg.det(u @ vt)
    return u @ correction @ vt, left, right


def coordinates(mol):
    return np.asarray(mol.GetConformer().GetPositions(), dtype=float)
