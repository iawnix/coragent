"""Job entrypoint; native attempts remain local descendants of this one Job."""
from pathlib import Path
import sys
import subprocess

SKILLS = Path(__file__).resolve().parents[2]
for part in ('_shared','chemical-input/scripts','crest/scripts','gaussian/scripts'):
    sys.path.insert(0,str(SKILLS/part))
from analysis_material import read_json
from ensemble_material import canonical
from gradient_contract import evaluate_evidence
from material import digest, object_fields
from neb_engine import neb
from path_contract import material, qst, settings
from path_gaussian import GaussianOptimizer
from path_process import write_json
from path_xtb import XtbCalculator
from scan_engine import scan
from search_cli import parse_arguments


def run(args):
    spec, sha = read_json(args.input); output = args.output_dir
    if args.operation == 'qst':
        text,result,m = qst(spec)
        if output.exists(): raise ValueError('new output directory required')
        result['input_file_sha256'] = sha
        output.mkdir(parents=True); (output/'ts.gjf').write_text(text)
        result['input_gjf_sha256'] = digest(text.encode())
        write_json(output/'result.json',result)
    elif args.operation.startswith('scan'):
        backend = args.operation.split('-')[1]
        cls = XtbCalculator if backend == 'xtb' else GaussianOptimizer
        result = scan(spec,output,backend,lambda m,s:cls(m,s,args.executable),max_points=args.max_points)
    elif args.operation == 'neb-xtb':
        result = neb(spec,output,lambda m,s:XtbCalculator(m,s,args.executable))
    else:
        object_fields(spec,('schema_version','material','settings'),'gradient input')
        if spec.get('schema_version') != 'chemical-gradient-input/1': raise ValueError('chemical-gradient-input/1 required')
        m=material(spec['material']); s=settings(spec['settings'],'xtb')
        calculator=XtbCalculator(m,s,args.executable)
        if output.exists(): raise ValueError('new output directory required')
        output.mkdir(parents=True)
        result={'schema_version':'chemical-gradient-result/1','input_file_sha256':sha,'status':'failed'}
        try:
            result['evaluation']=calculator.evaluate(m['coordinates'],output/'evaluation')
            evaluate_evidence(result['evaluation'],m,m['coordinates'],calculator.model)
            result['status']='completed'
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            result['error'] = {'type':type(exc).__name__, 'reason':str(exc)}
        finally: write_json(output/'result.json',result)
    return result


if __name__ == '__main__':
    result=run(parse_arguments())
    raise SystemExit(0 if result.get('status','completed') in ('completed','converged') else 1)
