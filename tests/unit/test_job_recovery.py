from pathlib import Path
import json
import sys
import time
import pytest
from research_agent.application.execution import dispatch
from research_agent.research.workspace import admit_research_workspace
from research_agent.application.job_state import execution
from research_agent.artifacts.registry import manifests
from research_agent.research.workspace import initialize_workspace
from research_agent.jobs import platforms_from_config, JobSpec, JobOutput, JobState


def platform():
    platforms, default = platforms_from_config()
    return platforms[default]


def finished(receipt):
    runtime = platform()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = runtime.status(receipt)
        if status.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.TIMED_OUT}:
            return status
        time.sleep(.02)
    raise AssertionError('Qrun job did not finish')


def spec(root, command, **kwargs):
    root.mkdir()
    return JobSpec(job_id='job_1', cwd=root, command=(sys.executable, '-c', command),
                   metadata={'resources': {'cpus': 1, 'memory_mb': 512}}, **kwargs)


@pytest.mark.parametrize('code', [0, 23])
def test_exit_receipt_survives_without_controller_polling(tmp_path, code):
    receipt = platform().start(spec(tmp_path / 'job', f'raise SystemExit({code})'))
    # The durable runtime writes its own result before any status observation.
    deadline = time.monotonic() + 5
    while not Path(receipt.cwd, 'status.exit').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert Path(receipt.cwd, 'status.exit').exists()
    recovered = platform().recover_receipt(receipt.job_id, Path(receipt.cwd))
    assert recovered.metadata['scheduler_id'] == receipt.metadata['scheduler_id']
    result = finished(recovered)
    assert result.state == (JobState.FAILED if code else JobState.SUCCEEDED)
    assert result.exit_code == code


def test_timeout_and_cancel_survive_controller_restart(tmp_path):
    receipt = platform().start(spec(tmp_path / 'timeout', 'import time; time.sleep(60)', timeout_seconds=.15))
    assert finished(receipt).state == JobState.TIMED_OUT
    receipt = platform().start(spec(tmp_path / 'cancel', 'import time; time.sleep(60)'))
    platform().cancel(receipt)
    assert finished(receipt).state == JobState.CANCELLED


def test_missing_outputs_do_not_rewrite_successful_exit(tmp_path):
    receipt = platform().start(spec(tmp_path / 'job', "open('empty','w').close()",
        outputs=(JobOutput('empty', required=True, min_bytes=1), JobOutput('missing', required=True))))
    assert finished(receipt).state == JobState.SUCCEEDED
    result = platform().collect(receipt)
    assert result['status']['exit_code'] == 0
    assert result['output_validation'] == {'complete': False, 'errors': [
        {'path': 'empty', 'error': 'too_small'}, {'path': 'missing', 'error': 'missing'}]}


def test_same_job_name_in_distinct_directories_keeps_separate_results(tmp_path):
    old = platform().start(spec(tmp_path / 'first', 'pass'))
    assert finished(old).state == JobState.SUCCEEDED
    new = platform().start(spec(tmp_path / 'second', 'raise SystemExit(23)'))
    assert finished(new).state == JobState.FAILED
    assert platform().status(old).state == JobState.SUCCEEDED


def workspace(root):
    initialize_workspace(root, 'ws_jobs', 'research')
    admit_research_workspace(root)


def test_job_attempt_collection_and_repeated_request_are_durable(tmp_path):
    workspace(tmp_path)
    source=tmp_path/'in.txt';source.write_text('input')
    request={'root':str(tmp_path),'request_id':'job_1','command':[sys.executable,'-c',"from pathlib import Path;Path('result').write_text(Path('data/source').read_text())"],
        'inputs':[{'source':str(source),'destination':'data/source'}], 'outputs':[{'path':'result','required':True,'min_bytes':1}]}
    receipt=dispatch('start',request)
    assert dispatch('start',request)['job_id']==receipt['job_id']
    for _ in range(100):
        if dispatch('status',{'root':str(tmp_path),'job_id':'job_1'})['state'] not in {'queued', 'submitted', 'running'}:break
        time.sleep(.02)
    result=dispatch('collect',{'root':str(tmp_path),'job_id':'job_1'})
    materials=list(manifests(tmp_path))
    assert execution(tmp_path, receipt['job_id'])['state']=='succeeded'
    assert result['output_validation']['complete']
    assert len(materials)>=2
    assert all(a['provenance']['job_id']==receipt['job_id'] for a in materials)
    again=dispatch('collect',{'root':str(tmp_path),'job_id':'job_1'})
    assert len(list(manifests(tmp_path)))==len(materials)
    with pytest.raises(ValueError,match='different parameters'):
        dispatch('start',{**request,'command':[sys.executable,'-c','pass']})


def test_caller_request_id_replays_without_submitting_again(tmp_path):
    workspace(tmp_path)
    request = {
        'root': str(tmp_path), 'request_id': 'skill_stable_submission',
        'command': [sys.executable, '-c', "from pathlib import Path; p=Path('count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"],
    }
    first = dispatch('start', request)
    for _ in range(100):
        if dispatch('status', {'root': str(tmp_path), 'job_id': first['job_id']})['state'] not in {'queued', 'submitted', 'running'}:
            break
        time.sleep(.02)
    second = dispatch('start', request)
    assert second['job_id'] == first['job_id']
    assert (Path(first['cwd']) / 'count').read_text() == '1'
    assert len(list((tmp_path/'operations/executions').glob('*.json'))) == 1
