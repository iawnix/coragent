"""Explicit-order trajectories and mode illustrations with provenance and fixed view."""
import csv
import math
from pathlib import Path
import re

import numpy as np

from analysis_material import numeric_array
from ensemble_material import canonical, checked, xyz_text
from local_diagnostics import coordinates, coordinate_rows
from material import object_fields


def source_digest(value):
    if not isinstance(value,str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',value):
        raise ValueError('source_sha256 must identify the source evidence')
    return value


def normalize(spec):
    object_fields(spec,('schema_version','material','frames','source_sha256','kind','coordinates','display_bonds',
                        'neb_result','mode','amplitude_angstrom','animation_frames','fps','model'), 'trajectory')
    if spec.get('schema_version')!='chemical-trajectory-input/1': raise ValueError('trajectory input schema required')
    m=checked(spec['material']); n=len(m['ids'])
    if m['coordinates'] is None or not 1<=n<=128: raise ValueError('trajectory requires 1..128 atoms with reference coordinates')
    kinds={'irc','neb','optimization','mode','other'}
    if spec.get('kind') not in kinds: raise ValueError('explicit trajectory kind required')
    if sum(spec.get(k) is not None for k in ('frames','neb_result','mode'))!=1: raise ValueError('provide frames, neb_result or mode exclusively')
    if 'amplitude_angstrom' in spec and spec.get('mode') is None: raise ValueError('amplitude only applies to a mode')
    raw=spec.get('frames'); source=spec.get('source_sha256'); source_status='supplied'; model=spec.get('model')
    if spec.get('neb_result') is not None:
        neb=spec['neb_result']
        if (not isinstance(neb,dict) or neb.get('schema_version') != 'chemical-neb-result/2'
                or neb.get('atom_ids')!=m['ids'] or neb.get('status') not in ('converged','step_limit','failed')
                or not isinstance(neb.get('images'),list) or not isinstance(neb.get('energies_hartree'),list)
                or len(neb['images'])!=len(neb['energies_hartree'])):
            raise ValueError('terminal NEB result with complete paired path and matching atom IDs required')
        if spec['kind']!='neb': raise ValueError('NEB source requires kind=neb')
        raw=[{'coordinates':xyz,'energy_hartree':e} for xyz,e in zip(neb['images'],neb['energies_hartree'])]
        if source is not None and source != canonical(neb): raise ValueError('NEB source digest mismatch')
        if model is not None and model != neb.get('model'): raise ValueError('NEB model declaration mismatch')
        source=canonical(neb);source_status=neb['status'];model=neb.get('model')
    elif spec.get('mode') is not None:
        if spec['kind']!='mode': raise ValueError('mode vectors require kind=mode')
        mode=spec['mode'];object_fields(mode,('vectors','representation','frequency_cm1'),'mode')
        if mode.get('representation')!='cartesian_displacement': raise ValueError('Cartesian displacement mode required; convert mass-weighted vectors first')
        vectors=numeric_array(mode.get('vectors'),(n,3),'mode vectors')
        norm=float(np.linalg.norm(vectors,axis=1).max())
        freq=mode.get('frequency_cm1')
        if norm<1e-12 or type(freq) not in (int,float) or not math.isfinite(freq): raise ValueError('nonzero finite mode and finite frequency required')
        amplitude=spec.get('amplitude_angstrom',.15)
        if type(amplitude) not in (int,float) or not math.isfinite(amplitude) or not 0<amplitude<=1: raise ValueError('mode amplitude must be (0,1] angstrom')
        raw=[{'coordinates':(m['coordinates']+vectors/norm*amplitude*np.sin(t)).tolist()} for t in np.linspace(0,2*np.pi,33)]
        source_status='mode_illustration_not_dynamics_or_irc'
    source_digest(source)
    if not isinstance(raw,list) or not 2<=len(raw)<=512: raise ValueError('2..512 ordered trajectory frames required')
    definitions=coordinates(spec,m)
    frames=[]
    for i,frame in enumerate(raw):
        object_fields(frame,('coordinates','energy_hartree'),'trajectory frame')
        xyz=numeric_array(frame.get('coordinates'),(n,3),'frame coordinates')
        e=frame.get('energy_hartree')
        if e is not None and (type(e) not in (int,float) or not math.isfinite(e)): raise ValueError('finite hartree energy or null required')
        frames.append({'index':i,'coordinates':xyz.tolist(),'energy_hartree':e,'geometry_sha256':canonical(xyz.tolist()),
                       'internal_coordinates':coordinate_rows(definitions,xyz)})
    if any(f['energy_hartree'] is not None for f in frames) and (not isinstance(model,dict) or not model):
        raise ValueError('common model declaration required for trajectory energy comparison')
    if spec['kind']=='mode' and any(f['energy_hartree'] is not None for f in frames): raise ValueError('mode illustrations cannot carry computed energies')
    bonds=spec.get('display_bonds',[])
    if not isinstance(bonds,list) or len(bonds)>512: raise ValueError('bounded display_bonds required')
    from local_diagnostics import ids
    for pair in bonds:
        if len(ids(pair,m,'display bond',2))!=2: raise ValueError('display bond needs exactly two IDs')
    fps=spec.get('fps',8); sample=spec.get('animation_frames',64)
    if type(fps) is not int or not 1<=fps<=30 or type(sample) is not int or not 2<=sample<=128: raise ValueError('fps 1..30 and animation_frames 2..128 required')
    return m,{'schema_version':'chemical-trajectory-result/1','source_sha256':source,'input_sha256':canonical(spec),
        'material_sha256':m['sha256'],'atom_ids':m['ids'],'kind':spec['kind'],'source_status':source_status,
        'model':model,'frames':frames,'display_bonds':bonds,'fps':fps,
        'mode': {**spec['mode'], 'amplitude_angstrom': spec.get('amplitude_angstrom', .15)} if spec.get('mode') is not None else None,
        'animation_frame_indices':np.unique(np.linspace(0,len(frames)-1,min(sample,len(frames))).round().astype(int)).tolist(),
        'scientific_validation':'not_assessed','scope':'Ordered supplied geometries; common fixed camera, no per-frame alignment, bond inference, trajectory completion or TS certification. Frame index is not physical time.'}


def plot_setup():
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    return plt


def draw_structure(ax,m,xyz,bonds,bounds,title):
    colors={'H':'#c4c9cf','C':'#343b44','N':'#367cd9','O':'#d94d4d','S':'#d5b930','F':'#4fbc8b','Cl':'#4fbc8b'}
    for pair in bonds:
        a,b=[m['ids'].index(i) for i in pair]
        ax.plot(*np.array([xyz[a],xyz[b]]).T,color='#8c939c',linewidth=2)
    for i,atom in enumerate(m['atoms']):
        ax.scatter(*xyz[i],s=40 if atom['element']=='H' else 95,c=colors.get(atom['element'],'#a87bce'),edgecolors='#657080',linewidths=.3)
    low,high=bounds
    for setter,j in ((ax.set_xlim,0),(ax.set_ylim,1),(ax.set_zlim,2)): setter(low[j],high[j])
    ax.set_box_aspect((1,1,1));ax.set_proj_type('ortho');ax.view_init(elev=20,azim=-60)
    ax.set_xlabel('x (Å)');ax.set_ylabel('y (Å)');ax.set_zlabel('z (Å)');ax.set_title(title)


def common_bounds(xyzs):
    flat=np.concatenate(xyzs);lo=flat.min(axis=0);hi=flat.max(axis=0)
    center=(lo+hi)/2;half=max(float((hi-lo).max())*.6,.5)
    return center-half,center+half


def write_trajectory(spec,output):
    m,result=normalize(spec)
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    plt=plot_setup()
    from PIL import Image
    xyzs=[np.array(f['coordinates']) for f in result['frames']]
    bounds=common_bounds(xyzs)
    figures=[]
    for index in result['animation_frame_indices']:
        fig=plt.figure(figsize=(6.4,4.8),dpi=80)
        try:
            ax=fig.add_subplot(111,projection='3d')
            draw_structure(ax,m,xyzs[index],result['display_bonds'],bounds,f"{result['kind']} · frame {index} (illustration)")
            fig.tight_layout();fig.canvas.draw()
            figures.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba()).copy()).convert('RGB'))
        finally:plt.close(fig)
    figures[0].save(out/'trajectory.gif',save_all=True,append_images=figures[1:],duration=round(1000/result['fps']),loop=0)
    for im in figures: im.close()
    (out/'trajectory.xyz').write_text(''.join(xyz_text(m['atoms'],x,f"{result['kind']} frame {i}; source {result['source_sha256']}") for i,x in enumerate(xyzs)))
    with (out/'profile.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['frame','energy_hartree']+[c['id']+' ['+c['unit']+']' for c in result['frames'][0]['internal_coordinates']])
        for f in result['frames']:writer.writerow([f['index'],f['energy_hartree']]+[c['value'] for c in f['internal_coordinates']])
    fig,axes=plt.subplots(3,1,figsize=(7,8),sharex=True)
    try:
        energy=[f['energy_hartree'] for f in result['frames']]
        finite=[e for e in energy if e is not None]
        axes[0].plot([np.nan if e is None else e-min(finite) for e in energy],marker='.')
        axes[0].set_ylabel('Relative E (hartree)')
        if not finite:axes[0].text(.5,.5,'Energy unavailable',transform=axes[0].transAxes,ha='center')
        for j,c in enumerate(result['frames'][0]['internal_coordinates']):
            ax=axes[1] if c['unit']=='angstrom' else axes[2]
            ax.plot([np.nan if f['internal_coordinates'][j]['value'] is None else f['internal_coordinates'][j]['value'] for f in result['frames']],label=c['id'])
        for ax,label in zip(axes[1:],('Distance (Å)','Angle / dihedral (degree)')):
            ax.set_ylabel(label)
            if ax.lines:ax.legend()
        axes[-1].set_xlabel('Frame index (not time)');fig.suptitle(f"{result['kind']}: {result['source_status']}")
        fig.tight_layout();fig.savefig(out/'profile.svg');fig.savefig(out/'profile.png',dpi=120)
    finally:plt.close(fig)
    from path_process import write_json
    result['files']=['trajectory.gif','trajectory.xyz','profile.csv','profile.svg','profile.png']
    write_json(out/'result.json',result)
    return result
