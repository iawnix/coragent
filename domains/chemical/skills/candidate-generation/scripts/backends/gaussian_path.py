"""Gaussian ground-spin gradients and NEB through the shared calculator contract."""
from pathlib import Path
import sys

SKILLS = next(parent for parent in Path(__file__).resolve().parents if (parent / '_shared').is_dir())
for part in ('_shared','chemical-input/scripts/materials','chemical-input/scripts/reaction',
             'crest/scripts','gaussian/scripts','energetics/scripts',
             'candidate-generation/scripts/path','candidate-generation/scripts/search',
             'candidate-generation/scripts/backends','candidate-generation/scripts/neb'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from electronic import GaussianElectronic
from gradient_contract import calculation,evaluate_evidence
from path_contract import material
from path_process import write_json
from search_cli import parse_arguments
from energy_common import schema


class GaussianPathCalculator:
    def __init__(self,m,settings,executable):
        self.material=m;self.calculator=GaussianElectronic(m,settings,executable)
        if self.calculator.settings['theory']!='ground':raise ValueError('Gaussian NEB only supports declared ground-spin surfaces')
        self.model={'calculator':'gaussian_ground_gradient','settings':self.calculator.settings,
            'charge':m['value']['charge'],'multiplicity':m['value']['multiplicity'],'electronic_state':m['value']['electronic_state'],'constraints':[]}

    def evaluate(self,xyz,directory):
        evidence=self.calculator.evaluate(xyz,directory)
        final=evidence['final']
        import numpy as np
        if not np.allclose(final['coordinates'],xyz,rtol=0,atol=2e-6):raise ValueError('Gaussian gradient geometry differs')
        value=calculation(self.material,xyz,self.model,final['energy_hartree'],final['gradient_hartree_per_angstrom'],
            {'source_sha256':evidence['source_sha256'],'printed_coordinates':final['coordinates'],'coordinate_precision_angstrom':2e-6,
             'state_continuity':evidence['state_continuity']})
        value['gradient']['unit']='hartree/angstrom'
        return value


def run(args):
    spec,sha=read_json(args.input)
    if args.operation!='gradient-gaussian':raise ValueError('this entrypoint only runs Gaussian gradients')
    schema(spec,'chemical-gradient-input/1',('material','settings'))
    m=material(spec['material']);calculator=GaussianPathCalculator(m,spec['settings'],args.executable)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    result={'schema_version':'chemical-gradient-result/1','input_file_sha256':sha,'status':'failed'}
    try:
        result['evaluation']=calculator.evaluate(m['coordinates'],args.output_dir/'evaluation')
        evaluate_evidence(result['evaluation'],m,m['coordinates'],calculator.model);result['status']='completed'
    finally:write_json(args.output_dir/'result.json',result)
    return result


if __name__=='__main__':
    result=run(parse_arguments())
    raise SystemExit(0 if result['status'] in ('completed','converged') else 1)
