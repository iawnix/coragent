"""Section-local target-state energies and derivatives, with no SCF substitution."""
import math
import re

import numpy as np
from analysis_material import numeric_array
from electronic_contract import BOHR_ANGSTROM, EV_HARTREE, route
from gaussian_io import (electronic_energy_evidence, orientation_blocks, parse_convergence,
    route_expectation, select_job_section, split_job_sections)
from xyz import PERIODIC_TABLE

NUM=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?'


def numeric(value):
    result=float(value.replace('D','E').replace('d','e'))
    if not math.isfinite(result): raise ValueError('nonfinite electronic output')
    return result


def force_table(lines,atoms):
    starts=[i for i,l in enumerate(lines) if 'Forces (Hartrees/Bohr)' in l]
    if len(starts)!=1: raise ValueError('one unambiguous Cartesian force table required per SCF cycle')
    i=starts[0];rows=[];started=False
    for line in lines[i+1:]:
        parts=line.split()
        if len(parts)==5 and parts[0].isdigit() and parts[1].isdigit():
            started=True
            if len(rows)>=len(atoms):raise ValueError('too many force rows')
            if int(parts[0])!=len(rows)+1 or int(parts[1])!=PERIODIC_TABLE.index(atoms[len(rows)][0]): raise ValueError('force atom order differs')
            rows.append([numeric(v) for v in parts[2:]])
        elif started:break
    forces=numeric_array(rows,(len(atoms),3),'force table')
    return (-forces/BOHR_ANGSTROM).tolist(),i


def states_in_cycle(lines,s,reference):
    states=[];selected=None;total=None;total_label=None;current=None
    header=re.compile(r'Excited State\s+(\d+)\s*:\s+(\S+)\s+('+NUM+r')\s+eV.*?f=\s*('+NUM+r')\s+<S\*\*2>=\s*('+NUM+r')')
    for line in lines:
        match=header.search(line)
        if match:
            root=int(match[1]);current={'root':root,'symmetry':match[2],'excitation_ev':numeric(match[3]),
                'oscillator_strength':numeric(match[4]),'spin_squared':numeric(match[5]),'printed_configurations':[]}
            if not current['symmetry'].startswith('Singlet-'): raise ValueError('non-singlet TD state outside selected scope')
            if any(row['root']==root for row in states): raise ValueError('duplicate TD root in cycle')
            states.append(current)
        elif 'This state for optimization and/or second-order correction.' in line:
            if current is None or selected is not None: raise ValueError('ambiguous selected-state marker')
            selected=current['root']
        elif re.search(r'Total Energy,\s*E\(',line):
            m=re.search(r'Total Energy,\s*E\(([^)]+)\)\s*=\s*('+NUM+r')',line)
            if not m or total is not None: raise ValueError('ambiguous excited-state total energy')
            total_label=m[1];total=numeric(m[2])
            if current is None or current['root']!=selected: raise ValueError('total energy is not bound to selected state')
        elif current is not None:
            m=re.match(r'\s*(\d+[AB]?)\s*(->|<-)\s*(\d+[AB]?)\s+('+NUM+r')\s*$',line)
            if m:current['printed_configurations'].append({'from':m[1],'direction':m[2],'to':m[3],'coefficient':numeric(m[4])})
    expected='TD-HF/TD-DFT' if s['theory']=='td' else 'CIS/TDA'
    if selected!=s['root'] or total_label!=expected or total is None or sorted(v['root'] for v in states)!=list(range(1,s['nstates']+1)):
        raise ValueError('complete requested TD roots, selected root and target total energy required')
    chosen=next(v for v in states if v['root']==selected)
    if abs((total-reference)*EV_HARTREE-chosen['excitation_ev'])>1e-4: raise ValueError('target energy does not match SCF plus selected excitation')
    if chosen['excitation_ev']<=0 or abs(chosen['spin_squared'])>s['spin_tolerance']: raise ValueError('unstable excitation or spin-contaminated selected state')
    return states,total


def parse_electronic(text,m,s,task):
    lines=text.splitlines()
    if len(split_job_sections(lines))!=1: raise ValueError('electronic adapter requires exactly one Gaussian job section')
    lines=select_job_section(lines)['lines'];joined='\n'.join(lines)
    version=re.search(r'Gaussian 16, Revision ([A-Z]\.\d+)',joined)
    if not version:raise ValueError('Gaussian 16 version evidence required')
    expected_route=route(m,s,task)
    from gaussian_io import extract_log_route
    if not route_expectation(expected_route,extract_log_route(lines),joined)['matched']: raise ValueError('electronic route readback differs')
    if 'Normal termination of Gaussian' not in joined or re.search(r'Error termination|Convergence failure|Convergence criterion not met|No convergence',joined,re.I):
        raise ValueError('electronic calculation did not terminate with convergence')
    declarations=re.findall(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)',joined)
    expected=(str(m['value']['charge']),str(m['value']['multiplicity']))
    if not declarations or any(pair!=expected for pair in declarations): raise ValueError('charge/reference multiplicity readback differs')
    positions=[i for i,l in enumerate(lines) if 'SCF Done:' in l]
    if not positions or len(positions)>s['max_cycles']+2: raise ValueError('missing or excessive SCF cycles')
    cycles=[]
    for ordinal,start in enumerate(positions):
        end=positions[ordinal+1] if ordinal+1<len(positions) else len(lines)
        chunk=lines[start:end];scf=re.search(r'SCF Done:\s+E\(([^)]+)\)\s*=\s*('+NUM+r')',chunk[0])
        label=('R' if m['value']['multiplicity']==1 else 'U')+s['functional']
        if not scf or re.sub('[^a-z0-9]','',scf[1].lower())!=re.sub('[^a-z0-9]','',label.lower()): raise ValueError('reference SCF method differs')
        reference=numeric(scf[2]);orientations=orientation_blocks(lines[:start],'Input orientation:')
        if not orientations:raise ValueError('input-orientation geometry required to bind original-axis forces')
        atoms=orientations[-1]
        if [a[0] for a in atoms]!=[a['element'] for a in m['atoms']]: raise ValueError('electronic geometry atom order differs')
        gradient,force_position=force_table(chunk,atoms)
        if s['theory']=='ground':
            if re.search(r'Excited State|Total Energy,\s*E\(', '\n'.join(chunk)): raise ValueError('unexpected target-state calculation')
            states=[];energy=reference
            if m['value']['multiplicity']==1:spin=0.;spin_source='restricted_closed_shell_determinant'
            else:
                spin_values=re.findall(r'S\*\*2 before annihilation\s+('+NUM+r')', '\n'.join(chunk))
                if len(spin_values)!=1: raise ValueError('unrestricted calculation needs pre-annihilation spin evidence')
                spin=numeric(spin_values[0]);spin_source='before_annihilation'
            desired=(m['value']['multiplicity']-1)/2
            if abs(spin-desired*(desired+1))>s['spin_tolerance']:raise ValueError('SCF spin contamination exceeds tolerance')
        else:
            states,energy=states_in_cycle(chunk,s,reference)
            totals=[i for i,l in enumerate(chunk) if re.search(r'Total Energy,\s*E\(',l)]
            if totals[0]>force_position: raise ValueError('force table precedes the target energy')
            spin=next(v['spin_squared'] for v in states if v['root']==s['root']);spin_source='selected_excited_state'
        cycles.append({'index':ordinal,'coordinates':[list(a[1:]) for a in atoms],'energy_hartree':energy,
            'reference_scf_energy_hartree':reference,'gradient_hartree_per_angstrom':gradient,'states':states,
            'spin_squared':spin,'spin_source':spin_source})
    if task=='sp' and (len(cycles)!=1 or not np.allclose(cycles[0]['coordinates'],m['coordinates'],rtol=0,atol=2e-6)):
        raise ValueError('single-point geometry/cycle binding differs')
    convergence,kind=parse_convergence(lines)
    if task=='opt':
        if kind!='stationary_point' or set(convergence)!={'Maximum Force','RMS Force','Maximum Displacement','RMS Displacement'}:
            raise ValueError('complete converged geometry optimization evidence required')
        for row in convergence.values():
            if type(row['value']) not in (int,float) or type(row['threshold']) not in (int,float) or row['converged']!='YES' or abs(row['value'])>row['threshold']:
                raise ValueError('optimization numeric criterion failed')
    return {'gaussian_revision':version[1],'cycles':cycles,'final':cycles[-1],'optimization_convergence':convergence if task=='opt' else None,
        'state_continuity':{'status':'not_assessed','reason':'Printed orbital labels/root indices do not establish inter-geometry wavefunction or transition-density overlap'},
        'scope':'Target-state energy/analytic gradient and spin diagnostics; no stable-wavefunction, minimum-frequency, root-continuity or global-state proof'}
