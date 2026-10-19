"""Deterministic native batch CLI used by local and simulated SSH tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    root = Path(os.environ['BATCH_FIXTURE_ROOT'])
    path = root / 'tasks.json'
    tasks = json.loads(path.read_text()) if path.exists() else []
    name, args = Path(sys.argv[0]).name, sys.argv[1:]
    if name in {'qsub', 'sbatch'}:
        index = len(tasks) + 1
        identity = str(index) if name == 'sbatch' else str(index) + '.fixture'
        request = (next(a.split('=', 1)[1] for a in args if a.startswith('--comment=')) if name == 'sbatch'
                   else args[args.index('-v')+1].split('=', 1)[1])
        record = {'id': identity, 'request_id': request, 'state': 'Q', 'exit': None, 'args': args, 'cwd': os.getcwd()}
        tasks.append(record)
        path.write_text(json.dumps(tasks))
        Path('qsub-arguments.json').write_text(json.dumps(args))
        count = Path('submission-count')
        count.write_text(str(int(count.read_text()) + 1) if count.exists() else '1')
        if not (root / 'defer').exists():
            run = subprocess.run(['/bin/sh', args[-1]], check=False)
            record.update(state='F', exit=run.returncode)
            path.write_text(json.dumps(tasks))
        if (root / 'lose-submit-response').exists():
            return 1
        print(identity)
    elif name in {'qdel', 'scancel'}:
        if (root / 'cancel-failure').exists():
            return 1
        for record in tasks:
            if record['id'] == args[-1]:
                record['cancel_requested'] = True
        path.write_text(json.dumps(tasks))
    elif name == 'qstat':
        if (root / 'query-failure').exists():
            return 1
        rows = {r['id']: {'job_state': r['state'], 'Variable_List': {'CORAGENT_REQUEST_ID': r['request_id']},
                         **({'Exit_status': r['exit']} if r['exit'] is not None else {})} for r in tasks}
        if 'json' in args:
            print(json.dumps({'Jobs': rows}))
        else:
            tree = ET.Element('Data')
            for identity, value in rows.items():
                job = ET.SubElement(tree, 'Job')
                value = {**value, 'Job_Id': identity, 'Variable_List': 'CORAGENT_REQUEST_ID='+value['Variable_List']['CORAGENT_REQUEST_ID']}
                for key, field in value.items():
                    ET.SubElement(job, key).text = str(field)
            print(ET.tostring(tree, encoding='unicode'))
    else:
        if (root / 'query-failure').exists():
            return 1
        for r in tasks:
            state = {'Q':'PENDING', 'R':'RUNNING', 'E':'COMPLETING', 'H':'SUSPENDED',
                     'F': 'COMPLETED' if r['exit'] == 0 else 'CANCELLED' if r.get('cancel_requested') else 'FAILED'}.get(r['state'], r['state'])
            if name == 'squeue' and r['state'] != 'F':
                print(f"{r['id']}|{r['request_id']}|{state}|fixture reason")
            if name == 'sacct':
                print(f"{r['id']}|{r['request_id']}|{state}|{r['exit'] or 0}:0")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
