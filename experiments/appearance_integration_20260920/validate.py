"""Frozen-data wiring validation. Never run new Codex or GPU inference."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import gs_entity_appearance_compact as compact
import gs_entity_appearance_scoring as scoring
import run_gs_temporal as pipeline
from run_gs_integrated import CPU, read, save, sha


def main():
    dest = Path(__file__).resolve().parent
    results = []
    for name in ('study2', 'study3'):
        upstream = ROOT / 'experiments/within_negative_review_20260920/full' / name
        old_base = ROOT / 'experiments/entity_appearance_separate_20260920' / name
        old_model = ROOT / 'experiments/entity_appearance_minimal_20260920' / name
        case = dest / name
        case.mkdir()
        for item in ('raw_manifest.json', 'narrative.json', 'global_entities', 'entities',
                     'identity_scope.json', 'alignment_method.json', 'within', 'pairs', 'calls'):
            if (upstream / item).exists():
                (case / item).symlink_to(upstream / item)
        # Exercise the public default, including CLI resolution of --stop-after.
        command = [CPU, str(ROOT / 'scripts/run_gs_integrated.py'), '--manifest',
                   str(case / 'raw_manifest.json'), '--narrative', str(case / 'narrative.json'),
                   '--output', str(case), '--gpu', '0', '--gpu-uuid', 'GPU-test', '--plan-only']
        jobs = json.loads(subprocess.check_output(command, text=True))
        assert jobs[-1]['stage'] == 'appearance_report'
        save(case / 'execution_plan.json', jobs)
        stages = []; started = time.time()
        canonical = case / 'appearance/canonical'; model = case / 'appearance/compact'
        for job in jobs[-5:]:
            before = time.time()
            if job['stage'] == 'appearance_dino':
                # Check every regenerated crop before reusing the frozen DINO result.
                for entity in read(canonical / 'manifest.json')['entities']:
                    eid = entity['global_entity_id']; new = canonical / 'entities' / eid
                    old = old_base / 'entities' / eid
                    a = read(new / 'input.json')['appearances']; b = read(old / 'input.json')['appearances']
                    assert len(a) == len(b)
                    for x, y in zip(a, b):
                        assert x.keys() == y.keys()
                        assert {k: v for k, v in x.items() if k != 'crop_path'} == {
                            k: v for k, v in y.items() if k != 'crop_path'}
                    shutil.copy2(old / 'dino.json', new / 'dino.json')
            elif job['stage'] == 'appearance_codex':
                (model / 'calls').symlink_to(old_model / 'calls')
                for entity in read(model / 'manifest.json')['entities']:
                    eid = entity['global_entity_id']; new = model / 'entities' / eid
                    old = old_model / 'entities' / eid
                    assert read(new / 'wire.json') == read(old / 'wire.json')
                    assert [x['sha256'] for x in read(new / 'images.json')] == [
                        x['sha256'] for x in read(old / 'images.json')]
                    shutil.copy2(old / 'codex.json', new / 'codex.json')
                # Exercise selected score dispatch, but fail if it tries any model call.
                with patch.object(sys, 'argv', job['command'][1:]), patch.object(
                        compact, 'call', side_effect=AssertionError('New model calls forbidden in replay')) as call:
                    scoring.main()
                    assert call.call_count == 0
            else:
                with (case / (job['stage'] + '.log')).open('w') as log:
                    subprocess.run(job['command'], check=True, stdout=log, stderr=subprocess.STDOUT)
            stages.append(dict(stage=job['stage'], status='success', seconds=time.time() - before,
                               validation_reuse=job['stage'] in ('appearance_dino', 'appearance_codex')))
        state = dict(status='success', seconds=time.time() - started, stages=stages, stop_after='full')
        r = pipeline.summarize(case, state)
        expected = next(s for s in read(ROOT / 'experiments/entity_appearance_scoring_20260920/results.json')['studies']
                        if s['study'] == name)
        for key in ('all_entities', 'multi_shot_entities', 'single_shot_entities'):
            assert r['appearance'][key] == expected[key]
        assert r['appearance']['total_tokens'] == expected['reused_total_tokens']
        r.update(validation_mode='frozen-data wiring replay, not fresh full pipeline inference',
                 new_model_calls=0, new_tokens=0, new_api_usd=0,
                 cost_note='All model usage in this validation summary is HISTORICAL reused usage; new API cost is zero.')
        r['appearance']['cost_note'] = r['cost_note']
        save(case / 'summary.json', r)
        results.append(dict(study=name, passed=True, **r['appearance']['all_entities'],
                            reused_tokens=r['appearance']['total_tokens'],
                            reused_api_equivalent_usd=r['appearance']['standard_api_equivalent_usd'],
                            audit=read(case / 'appearance/report/audit.json')))
    save(dest / 'validation.json', dict(passed=True, studies=results, new_model_calls=0, new_tokens=0,
                                      new_api_usd=0, fresh_frontend_or_gpu_run=False,
                                      source_hashes={str(p): sha(p) for p in [Path(__file__),
                                          ROOT / 'scripts/gs_appearance_integration.py',
                                          ROOT / 'scripts/run_gs_temporal.py', ROOT / 'scripts/run_gs_integrated.py']}))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
