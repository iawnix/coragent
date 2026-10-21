"""Geometry comparison and Gaussian input-binding utilities."""
import re
from pathlib import Path

import numpy as np
from rdkit import Chem

from gaussian_io import parse_log, select_job_section


def record(value, details=None, missing=False):
    return {'verdict':'pass' if value else 'inconclusive' if missing else 'fail', **({'details':details} if details is not None else {})}


def specification_markers(text):
    """Read only title lines starting with a known marker, including Gaussian wrapping.

    Never compact the whole log: a truncated digest must not consume unrelated text.
    Older marker names remain readable in historical scientific evidence.
    """
    lines = text.splitlines()
    markers, malformed = [], False
    for index, line in enumerate(lines):
        match = re.match(r'^\s*(?:CoRAgentSpec|CoRAgentSpec)\s+([0-9a-f]+)(.*)$', line)
        if not match:
            if re.match(r'^\s*(?:CoRAgentSpec|CoRAgentSpec)\b', line):
                malformed = True
            continue
        value, tail = match.groups()
        if len(value) < 64 and not tail.strip() and index + 1 < len(lines):
            continuation = re.match(r'^\s+([0-9a-f]+)(?=\s|$)', lines[index + 1])
            if continuation and len(value) + len(continuation[1]) == 64:
                value += continuation[1]
        if len(value) == 64 and (not tail or tail[0].isspace()):
            markers.append(value)
        else:
            malformed = True
    return markers, malformed


def log_checks(path, spec, atoms):
    parsed=parse_log(Path(path)); summary=parsed['summary']
    lines=select_job_section(Path(path).read_text(errors='replace').splitlines())['lines']
    text='\n'.join(lines)
    route=re.sub(r'\s+','',str(summary.get('gaussian_route') or '')).lower()
    token=f'{spec["method"]}/{spec["basis"]}'.lower()
    method=bool(re.search(r'(?<![a-z0-9_.-])'+re.escape(token)+r'(?=$|[^a-z0-9+*(),._-])',route))
    # Whitespace-free routes concatenate adjacent keywords; check route tokens before compaction too.
    method=method or token in [part.lower() for part in str(summary.get('gaussian_route') or '').split()]
    state=re.findall(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)',text,re.I)
    processors=re.findall(r'%nproc(?:shared)?\s*=\s*(\d+)',text,re.I) or re.findall(r'Will use up to\s+(\d+)\s+processors',text,re.I)
    memory=re.findall(r'%mem\s*=\s*(\d+)\s*(MB|GB)',text,re.I)
    expected_elements=[a.GetSymbol() for a in atoms.GetAtoms()]
    found=[a[0] for a in parsed['atoms']]
    markers, malformed = specification_markers(text)
    mismatch = any(m != spec.get('_bound_spec_sha256') for m in markers)
    marker_check = record(bool(markers) and not malformed and not mismatch,
                          {'status': 'mismatch' if mismatch else 'unreadable' if malformed else 'matched' if markers else 'missing',
                           'scope': 'Output title cross-check; execution provenance is recorded separately'},
                          missing=not mismatch and (not markers or malformed))
    checks={'specification_binding':marker_check,
            'normal_termination':record(summary['normal_termination'] and not summary['error_termination']),
            'method_basis':record(method),
            'processor_binding':record(bool(processors) and all(int(n)==spec['threads'] for n in processors),missing=not processors),
            'memory_binding':record(bool(memory) and all(int(n)*(1024 if unit.lower()=='gb' else 1)==spec['memory_mb'] for n,unit in memory),missing=not memory),
            'electronic_state':record(bool(state) and all((int(c),int(m))==(spec['charge'],spec['multiplicity']) for c,m in state),missing=not state),
            'atom_order':record(found==expected_elements,{'expected':expected_elements,'actual':found},missing=not found)}
    return parsed,checks,lines


def topology(mol, geometry):
    """Conservative all-atom connectivity by covalent radii; ambiguous distances never pass."""
    if len(geometry)!=mol.GetNumAtoms() or [a[0] for a in geometry]!=[a.GetSymbol() for a in mol.GetAtoms()]:
        return {'matches':False,'ambiguous':True,'reason':'atom count/order differs'}
    xyz=np.asarray([a[1:] for a in geometry],dtype=float)
    if not np.isfinite(xyz).all():
        raise ValueError('geometry_coordinates_must_be_finite')
    radii=[Chem.GetPeriodicTable().GetRcovalent(a.GetAtomicNum()) for a in mol.GetAtoms()]
    expected={tuple(sorted((b.GetBeginAtomIdx(),b.GetEndAtomIdx()))) for b in mol.GetBonds()}
    deviations=[];ambiguous=False
    for i in range(len(xyz)):
        for j in range(i+1,len(xyz)):
            ratio=float(np.linalg.norm(xyz[j]-xyz[i])/(radii[i]+radii[j]))
            bonded=(i,j) in expected
            if not np.isfinite(ratio) or ratio<0.55 or (bonded and ratio>1.25) or (not bonded and ratio<1.45):
                deviations.append({'atoms':[i+1,j+1],'expected_bond':bonded,'distance_ratio':ratio})
                ambiguous=ambiguous or 1.25<ratio<1.45
    # Assess only stereochemistry explicitly specified in the input graph.
    probe=Chem.Mol(mol);conformer=Chem.Conformer(mol.GetNumAtoms())
    for i,point in enumerate(xyz):conformer.SetAtomPosition(i,point)
    probe.RemoveAllConformers();probe.AddConformer(conformer)
    Chem.AssignStereochemistryFrom3D(probe,replaceExistingTags=True)
    Chem.AssignStereochemistry(probe,cleanIt=True,force=True)
    Chem.AssignStereochemistry(mol,cleanIt=True,force=True)
    stereo=[]
    for original,actual in zip(mol.GetAtoms(),probe.GetAtoms()):
        if original.HasProp('_CIPCode') and (not actual.HasProp('_CIPCode') or original.GetProp('_CIPCode')!=actual.GetProp('_CIPCode')):
            stereo.append(original.GetIdx()+1)
    bond_stereo=[]
    for original,actual in zip(mol.GetBonds(),probe.GetBonds()):
        if original.GetStereo() in (Chem.BondStereo.STEREOE,Chem.BondStereo.STEREOZ) and original.GetStereo()!=actual.GetStereo():
            bond_stereo.append([original.GetBeginAtomIdx()+1,original.GetEndAtomIdx()+1])
    return {'matches':not deviations and not stereo and not bond_stereo,'ambiguous':ambiguous,
            'bond_mismatches':deviations,'stereo_mismatches':stereo,'bond_stereo_mismatches':bond_stereo}


def aligned_rmsd(a,b):
    """Least-squares proper rotation of the supplied atom correspondence; never relabel atoms."""
    if [x[0] for x in a]!=[x[0] for x in b] or not a:return None
    x=np.asarray([v[1:] for v in a],dtype=float);y=np.asarray([v[1:] for v in b],dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('geometry_coordinates_must_be_finite')
    x-=x.mean(axis=0);y-=y.mean(axis=0)
    u,_,vt=np.linalg.svd(x.T@y);fix=np.eye(3);fix[-1,-1]=np.linalg.det(u@vt)
    return float(np.sqrt(np.mean(np.sum((x@u@fix@vt-y)**2,axis=1))))
