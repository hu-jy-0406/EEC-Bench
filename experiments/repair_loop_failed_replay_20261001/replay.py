#!/usr/bin/env python3
"""Replay every recorded VL/VV validation failure through the new repair loop.

Each case starts from the exact model output that failed in production
(round 0, no new call) and continues that same API conversation with the
all-errors repair loop until the output validates or 8 rounds are used.
Original experiment directories are read only; all new calls are written here.
Downstream stages are not rerun: this measures whether the failing stage is
resolved and how many repair rounds it needs.
"""
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from glob import glob
from pathlib import Path

HERE = Path(__file__).resolve().parent
EEC = HERE.parents[1]
sys.path.insert(0, str(EEC / 'scripts'))

import vl_vv_repair_loop as loop  # noqa: E402
import run_vl_vv_detection as detection  # noqa: E402
import run_vl_vv_issue_discovery as discovery  # noqa: E402
import run_vl_vv_issue_review as review  # noqa: E402
import gs_shot_prompt_recovery as recovery  # noqa: E402

A = EEC / 'experiments/vl_vv_multimodel_first200_run02'
B = EEC / 'experiments/vl_vv_multimodel_first200_run02_b'

# (controller root, model, priority, attempt, stage); from events.jsonl failures.
FAILURES = [
    (A, 'wan21', 3, 1, 'review'), (A, 'holocine', 15, 1, 'match'), (A, 'cinetrans', 25, 1, 'discovery'),
    (A, 'wan22', 42, 1, 'match'), (A, 'holocine', 53, 1, 'discovery'), (A, 'wan22', 56, 1, 'discovery'),
    (A, 'storymem', 57, 1, 'match'), (A, 'wan22', 67, 1, 'discovery'), (A, 'wan22', 67, 2, 'discovery'),
    (A, 'holocine', 72, 1, 'match'), (A, 'storymem', 73, 1, 'discovery'), (A, 'storymem', 73, 2, 'discovery'),
    (A, 'holocine', 73, 3, 'match'), (A, 'holocine', 73, 4, 'discovery'), (A, 'holocine', 73, 5, 'discovery'),
    (A, 'storymem', 73, 6, 'match'), (B, 'wan22', 101, 1, 'binding'), (B, 'cinetrans', 102, 1, 'review'),
]


def read(path):
    return json.loads(Path(path).read_text())


def locate(root, model, priority, attempt, stage):
    base = Path(glob(f'{root}/{model}/priority_{priority:03d}_*/attempt_{attempt:02d}')[0])
    case = base / 'work/case'
    if stage == 'match':
        folder = case / 'global_match/attempts/attempt_00'
        local = detection.local_rows(case)[2]
        return folder, lambda r: (detection.exact_once_errors(r, local), r)
    if stage == 'discovery':
        folder = base / 'results/issue_discovery/call'
        ledger, manifest = read(case / 'episode_entities.json'), read(case / 'raw_manifest.json')
        return folder, lambda r: (discovery.result_errors(r, ledger, manifest), r)
    if stage == 'review':
        folder = base / 'results/issue_review/call'
        manifest = read(case / 'raw_manifest.json')
        candidates = review.validate_discovery_result(read(base / 'results/issue_discovery/result.json'), manifest)

        def collect(r):
            normalized, _ = review.normalize_review_frame_references(r, manifest)
            return review.review_errors(normalized, candidates, manifest)
        return folder, collect
    if stage == 'binding':
        failed = [Path(p).parent for p in glob(f'{case}/shot_prompt_recovery/calls/*_binding/status.json')
                  if read(p)['status'] == 'failed']
        folder = failed[0]
        payload = read(folder / 'input.json')
        return folder, lambda r: recovery.binding_errors(r, payload)
    raise ValueError(stage)


def replay(item):
    root, model, priority, attempt, stage = item
    name = f'p{priority:03d}_{model}_a{attempt:02d}_{stage}'
    out = HERE / 'cases' / name
    started = time.time()
    record = dict(case=name, model=model, priority=priority, attempt=attempt, stage=stage)
    try:
        source, collect = locate(*item)
        status = read(source / 'status.json')
        record.update(source_call=str(source), stage_model=status.get('model'), stage_reasoning=status.get('reasoning'))
        out.mkdir(parents=True, exist_ok=False)
        # Original task instructions (prompt.txt minus its INPUT block), used
        # only if the stored conversation cannot be continued.
        task_prompt = out / 'original_task_prompt.txt'
        task_prompt.write_text((source / 'prompt.txt').read_text().split('\nINPUT:\n', 1)[0])
        value, raw, usage, audit = loop.call_with_repair(
            out / 'call', read(source / 'input.json'), read(source / 'request.json')['images'], 1800,
            prompt_path=task_prompt,
            schema=read(source / 'output.schema.json'), model=status['model'], reasoning=status['reasoning'],
            collect_errors=collect, first_response=read(source / 'response.json'), first_folder=source,
            stage=f'replay {name}')
        record.update(status='resolved', repair_rounds=audit['repair_rounds'])
    except Exception as exc:
        record.update(status='unresolved', error=str(exc)[:2000], traceback=traceback.format_exc()[-3000:])
    audit_path = out / 'call_repair_audit.json'
    if audit_path.is_file():
        audit = read(audit_path)
        rounds = audit['rounds']
        record['round0_errors'] = rounds[0]['errors']
        record['errors_per_round'] = [r['error_count'] for r in rounds]
        record['continuation_failures'] = sum('continuation_failure' in r for r in rounds)
        # Round-0 usage belongs to the original production call, not this replay.
        record['new_usage'] = audit.get('usage', [])[len(loop._usage(Path(record['source_call']))):]
        record['repair_rounds'] = audit.get('repair_rounds', len(rounds) - 1)
    record['seconds'] = round(time.time() - started, 1)
    (out.parent / f'{name}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(case=name, status=record['status'], rounds=record.get('repair_rounds'))), flush=True)
    return record


def main():
    (HERE / 'cases').mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(replay, FAILURES))
    (HERE / 'records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
