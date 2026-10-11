"""Bounded native Gaussian state calculations and independent state-character audit."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

SKILLS=Path(__file__).resolve().parents[2]
for part in ('_shared','chemical-input/scripts','energetics/scripts','candidate-generation/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from electronic_cli import parse_arguments
from electronic_contract import electronic_material, input_text, settings, state_scope
from electronic_parse import parse_electronic
from energy_common import canonical, fields, schema
from material import build_material, digest
from path_process import invoke,write_json
from state_tracking import track_states


class GaussianElectronic:
    def __init__(self,m,config,executable):
        electronic_material(m['value'])
        self.material=m;self.settings=settings(config);state_scope(m,self.settings);self.executable=shutil.which(executable)
        if not self.executable:raise ValueError('configured Gaussian executable unavailable')

    def evaluate(self,xyz,directory,task='sp'):
        directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=False)
        text=input_text(self.material,self.settings,task,xyz);inp=directory/'input.gjf';inp.write_text(text)
        scratch=directory/'scratch';scratch.mkdir()
        try:
            invoke([self.executable],directory,self.settings['timeout_seconds'],self.settings['threads'],stdin=inp,extra_env={'GAUSS_SCRDIR':str(scratch)})
        finally:
            shutil.rmtree(scratch)
        log=directory/'program.out'
        if log.stat().st_size>64*1024*1024:raise ValueError('electronic log exceeds 64 MiB')
        bound=dict(self.material,coordinates=xyz)
        parsed=parse_electronic(log.read_text(errors='replace'),bound,self.settings,task)
        parsed.update(schema_version='chemical-electronic-evaluation/1',atom_ids=self.material['ids'],
            elements=[a['element'] for a in self.material['atoms']],charge=self.material['value']['charge'],
            multiplicity=self.material['value']['multiplicity'],electronic_state=self.material['value']['electronic_state'],
            model={k:v for k,v in self.settings.items() if k not in ('threads','memory_mb','timeout_seconds','max_cycles')},
            input_sha256=digest(inp.read_bytes()),source_sha256=digest(log.read_bytes()),coordinate_unit='angstrom',
            gradient_unit='hartree/angstrom',gradient_quantity='dE/dR')
        write_json(directory/'evaluation.json',parsed)
        return parsed


def derived_material(m,xyz,evidence):
    spec={'schema_version':'chemical-material-input/1','format':'xyz',
        'text':str(len(m['atoms']))+'\nElectronic geometry; identity unassigned\n'+''.join(a['element']+' '+' '.join(format(float(v),'.16g') for v in row)+'\n' for a,row in zip(m['atoms'],xyz)),
        'atom_ids':m['ids'],'charge':m['value']['charge'],'multiplicity':m['value']['multiplicity'],
        'electronic_state':{k:v for k,v in m['value']['electronic_state'].items() if k in ('kind','label','method','root','note')}}
    result,_=build_material(spec,evidence['source_sha256']);result['derivation']={'operation':'electronic_calculation','source_material_sha256':m['sha256'],'source_graph':m['value'].get('graph')}
    return result


def run(args):
    spec,sha=read_json(args.input)
    if args.operation=='track':
        result=track_states(spec);result['input_file_sha256']=sha
        args.output_dir.mkdir(parents=True,exist_ok=False);write_json(args.output_dir/'result.json',result)
        return result
    schema(spec,'chemical-electronic-input/1',('material','settings','task'))
    m=electronic_material(spec['material']);s=settings(spec['settings']);task=spec.get('task')
    input_text(m,s,task) # Validate before launching any process.
    calculator=GaussianElectronic(m,s,args.executable)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    result={'schema_version':'chemical-electronic-result/1','input_file_sha256':sha,'status':'failed','settings':s}
    try:
        evidence=calculator.evaluate(m['coordinates'],args.output_dir/'calculation',task)
        result.update(status='completed',evaluation=evidence,material=derived_material(m,evidence['final']['coordinates'],evidence))
        write_json(args.output_dir/'material.json',result['material'])
    except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
        result['error']={'type':type(exc).__name__,'reason':str(exc)}
    finally:write_json(args.output_dir/'result.json',result)
    return result


if __name__=='__main__':
    result=run(parse_arguments())
    raise SystemExit(0 if result.get('status') in ('completed','consistent_character','root_changed','inconclusive') else 1)
