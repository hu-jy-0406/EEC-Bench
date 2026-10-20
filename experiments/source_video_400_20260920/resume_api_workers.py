#!/usr/bin/env python3
"""Resume one validated runtime-only update at an idle batch boundary."""
import fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if not os.environ.get('SLURM_JOB_ID'):
    raise RuntimeError('Existing compute allocation required')
transition=(ROOT/'continuation.lock').open('a')
print('Waiting for the existing coordinator to finish its batch.',flush=True)
fcntl.flock(transition,fcntl.LOCK_EX)
with (ROOT/'campaign.lock').open('a') as handle:
    fcntl.flock(handle,fcntl.LOCK_EX)
    for attempt in range(50):
        state=json.loads((ROOT/'runtime.json').read_text())
        if state['status'] not in ('running','waiting_live_downloader_lock'):
            break
        time.sleep(.1)
    assert state['status']=='paused_at_batch_boundary',state
    marker=ROOT/'pause_after_batch'
    request=json.loads(marker.read_text())
    assert request['reason']=='validated_api_workers6_runtime_reload'
    report=json.loads((ROOT/'preflight/api-workers6/validation.json').read_text())
    assert report['passed'] and report['runtime_only']
    deferred=request['deferred_install']
    assert deferred['destination']=='extraction/run_extraction.py'
    runner=ROOT/deferred['destination']
    staged=(ROOT/deferred['staged_path']).read_bytes()
    assert hashlib.sha256(staged).hexdigest()==deferred['after_sha256']
    assert hashlib.sha256(runner.read_bytes()).hexdigest() in (
        deferred['before_sha256'],deferred['after_sha256'])
    for relative,digest in request['code_sha256'].items():
        content=staged if relative==deferred['destination'] else (ROOT/relative).read_bytes()
        assert hashlib.sha256(content).hexdigest()==digest,relative
    for relative,digest in report['frozen_sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
    config=json.loads((ROOT/'construction_config.json').read_text())
    assert config['api_workers']==6
    temporary=runner.with_suffix('.runtime-update.tmp')
    temporary.write_bytes(staged)
    temporary.replace(runner)
    marker.unlink()
print(json.dumps({'status':'resuming_runtime_update','api_workers':6,'previous':state}),flush=True)
sys.exit(subprocess.call([sys.executable,'-u',str(ROOT/'campaign.py'),'run',
    '--batch-size','12','--max-rounds','180','--api-workers','6']))
