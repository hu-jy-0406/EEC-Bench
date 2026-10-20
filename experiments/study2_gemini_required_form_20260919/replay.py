"""One fresh Gemini review on explicitly frozen Study2 evidence; no retry."""
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent
BENCH = ROOT.parents[1]
ROOT = ROOT / 'indexed_form'
sys.path.insert(0, str(BENCH / 'scripts'))
import gs_gemini_backend as backend
from review_aligned_entity_identities import validate
from run_isolated_shot_static_3d import owned_compute_job


def main():
    allocation = owned_compute_job()
    import psutil
    cores = sorted(os.sched_getaffinity(0))
    busy = psutil.cpu_percent(interval=1, percpu=True)
    assert len(cores) == 1 and busy[cores[0]] < 15, 'CPU preflight failed'
    ROOT.mkdir(exist_ok=False)
    source = BENCH / 'experiments/study2_gemini35_cpu_20260919/run01'
    call = source / 'calls/identity_review_attempt1'
    out = ROOT / 'call'
    out.mkdir(exist_ok=False)
    inputs = [call / n for n in ['input.json', 'wire_input.json', 'prompt.txt', 'output.schema.json']]
    images = json.loads((source / 'identity_review_images.json').read_text())
    sources = inputs + [Path(f['path']) for f in images]
    hashes = {str(p): backend.sha(p.read_bytes()) for p in sources}
    for frame in images:
        assert hashes[frame['path']] == frame['sha256']
    for path in inputs:
        shutil.copy2(path, out / path.name)
    snapshot = ROOT / 'source_snapshot'
    snapshot.mkdir()
    for name in ['gs_gemini_backend.py', 'review_aligned_entity_identities.py', 'gs_identity_population.py']:
        path = BENCH / 'scripts' / name
        hashes[str(path)] = backend.sha(path.read_bytes())
        shutil.copy2(path, snapshot / name)
    backend.save(ROOT / 'sources.json', hashes)
    backend.save(out / 'request.json', dict(images=images, frozen_source=str(call)))
    command = ['gemini-api', '--model', backend.MODEL, '--output-schema', str(out / 'output.schema.json'),
               '--output-last-message', str(out / 'response.json')]
    for frame in images:
        command.extend(['--image', frame['path']])
    started = time.time()
    state = dict(status='running', allocation=allocation, cpu_cores=cores,
        model=backend.MODEL, reasoning='medium', source=str(source), frozen_upstream_reuse=True,
        scope='aligned_identity_review_only', retries=0, presence_score=None, spatial_score=None)
    backend.save(ROOT / 'result.json', state)
    try:
        backend.dispatch(command, (out / 'prompt.txt').read_text(), ROOT,
                         out / 'events.jsonl', out / 'stderr.log', 1800)
        result = json.loads((out / 'response.json').read_text())
        payload = json.loads((out / 'input.json').read_text())
        state.update(reviewed_initial_groups=len(result['initial_group_reviews']),
            expected_initial_groups=len(payload['initial_matching']['groups']),
            final_groups=len(result['matching']['groups']), noncommon_checks=len(result['noncommon_checks']),
            expected_noncommon_checks=sum(g['identity'] == 'unmatched' for g in result['matching']['groups']))
        validate(result, payload)
        state.update(status='success', original_semantic_validator_passed=True)
    except BaseException as exc:
        state.update(status='failed', error=repr(exc), original_semantic_validator_passed=False)
        raise
    finally:
        unchanged = all(backend.sha(Path(p).read_bytes()) == h for p, h in hashes.items())
        state.update(seconds=time.time() - started, all_frozen_sources_unchanged=unchanged)
        usage = out / 'gemini_usage.json'
        if usage.exists():
            state['usage'] = json.loads(usage.read_text())['normalized']
        backend.save(ROOT / 'result.json', state)
        print(json.dumps(state, indent=2), flush=True)
        assert unchanged, 'Frozen source changed'


if __name__ == '__main__':
    main()
