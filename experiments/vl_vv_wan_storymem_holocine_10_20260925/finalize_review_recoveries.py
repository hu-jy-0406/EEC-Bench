#!/usr/bin/env python3
"""Mark outputs recovered from saved reviewer responses as complete."""
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
MODELS = ('wan22', 'storymem', 'holocine')


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    recovered = []
    for model in MODELS:
        for case in sorted((EXP / model).glob('*/case')):
            output = case / 'issue_review_recovered'
            result = output / 'result.json'
            state_path = output / 'run.json'
            timing_path = case / 'case_timing.json'
            if not result.is_file() or not state_path.is_file() or not timing_path.is_file():
                continue
            state = read(state_path)
            reviewed_result = read(result)
            timing = read(timing_path)
            reused_from = reviewed_result.get('review_run', {}).get('reused_response_from')
            if state.get('status') != 'success' or reused_from is None:
                continue
            started = int(state['started'] * 1_000_000_000)
            finished = int((state['started'] + state.get('seconds', 0)) * 1_000_000_000)
            recovery_path = case / 'case_recovery_stages.json'
            recovery = read(recovery_path) if recovery_path.is_file() else {
                'protocol': 'vl_vv_case_recovery_timing_v1', 'stages': []}
            if not any(row.get('stage') == 'review_response_validation_recovery' for row in recovery['stages']):
                recovery['stages'].append(dict(stage='review_response_validation_recovery',
                                               started_epoch_ns=started, finished_epoch_ns=finished,
                                               seconds=max(0, (finished-started)/1_000_000_000),
                                               status='success', api_calls=0,
                                               source_response=reused_from))
            recovery['status'] = 'success'
            recovery['recovery_seconds'] = sum(row.get('seconds', 0) for row in recovery['stages'])
            save(recovery_path, recovery)
            timing['review_status'] = 'success'
            if timing.get('pipeline_status') == 'success':
                timing['status'] = 'success'
            timing['finished_epoch_ns'] = max(timing.get('finished_epoch_ns', 0), finished)
            save(timing_path, timing)
            recovered.append(dict(model=model, episode=case.parent.name,
                                  issues=reviewed_result.get('review_run', {}).get('reviewed_issue_count', 0),
                                  api_calls=0))
    print(json.dumps({'recovered_review_outputs': len(recovered), 'cases': recovered}, ensure_ascii=False))


if __name__ == '__main__':
    main()
