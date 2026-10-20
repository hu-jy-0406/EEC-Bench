#!/usr/bin/env python3
"""Run five full VL/VV pipelines per episode, preserving strict priority order."""
import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = Path(__file__).resolve().parent
PREPARE = EXPERIMENT / 'prepare_case.py'
PIPELINE = ROOT / 'EECBench/scripts/run_vl_vv_pipeline.py'
API = ROOT / 'EECBench/scripts/openai_api_env.sh'
MODEL_ORDER = ['wan21', 'cinetrans', 'wan22', 'storymem', 'holocine']
VACE_PYTHON = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
GPU_PYTHON = VACE_PYTHON
PREPARE_PYTHON = VACE_PYTHON
REVIEW_PYTHON = VACE_PYTHON
STOP_REQUESTED = False
# Evaluator chains run by run_vl_vv_pipeline.py --discovery-protocol and
# --review-protocol, and the scoring protocol each review protocol leads to.
# Discovery v1 is the historical chain of the first-200 multimodel runs
# (review v1); discovery v2 adds the checklist and non-exclusive V-L/V-V labels,
# and discovery v3 the checklist with one label per issue (linked pairs), each
# with review v4 (verdicts on the core problem of each label; default) or
# review v2 (the previous per-label review).  Discovery v5 (2026-10-09) is the
# branch-separated chain: separate V-L and V-V detection, review v6 (separate
# V-L / V-V reviews) and scoring v5 (separate V-L, V-V and unintentional-entity
# scores).  An experiment directory keeps one chain for its whole life.
SCORING_PROTOCOLS = {'v1': 'vl_vv_episode_scoring_v2', 'v2': 'vl_vv_episode_scoring_v3',
                     'v4': 'vl_vv_episode_scoring_v3', 'v5': 'vl_vv_episode_scoring_v3',
                     'v6': 'vl_vv_episode_scoring_v5'}  # keyed by review protocol
REVIEW_PROTOCOLS = {'v1': ('v1',), 'v2': ('v5', 'v4', 'v2'), 'v3': ('v5', 'v4', 'v2'),
                    'v4': ('v5', 'v4', 'v2'), 'v5': ('v6',)}  # first = default for a new directory
# Model stages whose run.json token_cost belongs to the evaluation, per chain.
EVALUATION_STAGES = {'single_list': ('issue_discovery', 'issue_review', 'episode_scoring'),
                     'branch': ('vl_detection', 'vv_detection', 'vl_review', 'vv_review', 'episode_scoring')}
LEGACY_DISCOVERY_PROTOCOL = 'v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)


def event(path, kind, **fields):
    row = dict(timestamp_utc=now(), event=kind, **fields)
    with Path(path).open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def safe_id(task):
    return f'priority_{task["generation_priority"]:03d}__{task["model_id"]}'


def attempt_number(root, task):
    legacy = root / 'cases' / f'priority_{task["generation_priority"]:03d}' / task['model_id']
    if legacy.exists():
        previous = [int(p.name.split('_')[-1]) for p in legacy.glob('attempt_*') if p.name.split('_')[-1].isdigit()]
        return max(previous, default=0) + 1
    directory = root / task['model_id'] / f'priority_{task["generation_priority"]:03d}_{task["episode_id"]}'
    if not directory.exists():
        return 1
    previous = [int(p.name.split('_')[-1]) for p in directory.glob('attempt_*') if p.name.split('_')[-1].isdigit()]
    return max(previous, default=0) + 1


def task_dirs(root, task, attempt):
    legacy_base = root / 'cases' / f'priority_{task["generation_priority"]:03d}' / task['model_id']
    if legacy_base.exists():
        base = legacy_base / f'attempt_{attempt:02d}'
        out = root / 'results' / f'priority_{task["generation_priority"]:03d}' / task['model_id'] / f'attempt_{attempt:02d}'
        return base, base / 'case', out

    task_base = root / task['model_id'] / f'priority_{task["generation_priority"]:03d}_{task["episode_id"]}' / f'attempt_{attempt:02d}'
    work = task_base / 'work'
    case = work / 'case'
    output = task_base / 'results'
    return work, case, output


def valid_success(row, scoring_protocol=SCORING_PROTOCOLS[LEGACY_DISCOVERY_PROTOCOL]):
    try:
        run = read(Path(row['output_dir']) / 'run.json')
        score = read(Path(row['output_dir']) / 'episode_scoring/result.json')
        return run.get('status') == 'success' and score.get('status') == 'success' and score.get('protocol') == scoring_protocol
    except (OSError, KeyError, ValueError, TypeError):
        return False


def resolve_discovery_protocol(progress, requested):
    """The evaluator chain for this experiment directory.

    An existing directory keeps the chain it started with (directories created
    before the choice existed are the historical v1 chain); a different
    request is refused so v1 and v2 results never mix.  A new directory needs
    an explicit choice.
    """
    if progress is not None:
        recorded = progress.get('discovery_protocol', LEGACY_DISCOVERY_PROTOCOL)
        if requested is not None and requested != recorded:
            raise ValueError(f'This experiment directory runs discovery protocol {recorded}; '
                             f'use a fresh --exp-dir for {requested}')
        return recorded
    if requested is None:
        raise ValueError('Choose --discovery-protocol v1 (historical chain), v2 (checklist, multi-label), v3 (checklist, one label per issue), v4 (v3 + episode-wide entity descriptions) or v5 (separate V-L / V-V branches) for a new experiment directory')
    return requested


def resolve_review_protocol(progress, discovery_protocol, requested):
    """The review protocol for this experiment directory.

    An existing directory keeps its recorded review protocol; a directory
    recorded before review protocols were recorded ran the review of its
    discovery protocol (v1 -> v1, v2 -> v2).  A different request is refused.
    A new directory uses the request or the default for its discovery protocol.
    Review v3 (partly true verdicts) was removed on 2026-10-06.
    """
    allowed = REVIEW_PROTOCOLS[discovery_protocol]
    if requested is not None and requested not in allowed:
        raise ValueError(f'Review protocol {requested} does not apply to discovery protocol {discovery_protocol} '
                         f'(allowed: {list(allowed)})')
    if progress is not None:
        recorded = progress.get('review_protocol', discovery_protocol)
        if recorded not in SCORING_PROTOCOLS:
            raise ValueError(f'This experiment directory recorded review protocol {recorded}, which is no longer available')
        if requested is not None and requested != recorded:
            raise ValueError(f'This experiment directory runs review protocol {recorded}; use a fresh --exp-dir for {requested}')
        return recorded
    return requested or allowed[0]


def token_cost(run_path):
    try:
        value = read(run_path)
    except (OSError, ValueError):
        return None
    return value.get('token_cost') or value.get('usage_cost')


def usage_from(value):
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = [value]
    else:
        rows = []
    total = dict(uncached_input_tokens=0, cached_input_tokens=0, output_tokens=0, api_calls=0)
    for row in rows:
        if not isinstance(row, dict):
            continue
        cached = int(row.get('cached_input_tokens') or 0)
        if 'uncached_input_tokens' in row:
            uncached = int(row.get('uncached_input_tokens') or 0)
        else:
            uncached = max(0, int(row.get('input_tokens') or 0) - cached)
        total['uncached_input_tokens'] += uncached
        total['cached_input_tokens'] += cached
        total['output_tokens'] += int(row.get('output_tokens') or 0)
        total['api_calls'] += 1
    return total


def combine_usage(parts):
    total = dict(uncached_input_tokens=0, cached_input_tokens=0, output_tokens=0, api_calls=0)
    for part in parts:
        for key in total:
            total[key] += int(part.get(key) or 0)
    total['estimated_usd'] = round(
        total['uncached_input_tokens'] * 0.10 / 1_000_000
        + total['cached_input_tokens'] * 0.01 / 1_000_000
        + total['output_tokens'] * 0.50 / 1_000_000, 9)
    total['pricing_basis'] = 'GPT-6 Luna standard API estimate: USD 0.10/M uncached input, USD 0.01/M cached input, USD 0.50/M output; cached input is a subset, not an actual bill.'
    return total


def score_record(task, output):
    scoring = read(output / 'episode_scoring/result.json')
    scores = scoring['scores']
    vv = scores.get('v_v', {})
    chain = 'branch' if (output / 'vl_detection').is_dir() else 'single_list'
    stage_names = EVALUATION_STAGES[chain]
    stage_costs = {
        name: token_cost(output / name / 'run.json')
        for name in stage_names
    }
    case = Path(read(output / 'run.json')['case'])
    frontend_parts = []
    entities_run = read(case / 'entities/run.json')
    for shot in entities_run.get('shots', []):
        frontend_parts.append(usage_from(shot.get('usage')))
    recovery_calls = case / 'shot_prompt_recovery/calls'
    if recovery_calls.is_dir():
        for path in sorted(recovery_calls.glob('*/status.json')):
            frontend_parts.append(usage_from(read(path).get('usage')))
    match_attempts = case / 'global_match/attempts'
    if match_attempts.is_dir():
        for path in sorted(match_attempts.glob('*/status.json')):
            frontend_parts.append(usage_from(read(path).get('usage')))
    frontend_usage = combine_usage(frontend_parts)
    scoring_parts = []
    for name in stage_names:
        cost = stage_costs[name]
        if isinstance(cost, dict):
            result = read(output / name / 'result.json')
            if name == 'issue_review':
                calls = result.get('review_run', {}).get('usage', [])
            else:
                calls = result.get('usage', [])
            scoring_parts.append(dict(uncached_input_tokens=int(cost.get('uncached_input_tokens') or 0),
                                      cached_input_tokens=int(cost.get('cached_input_tokens') or 0),
                                      output_tokens=int(cost.get('output_tokens') or 0),
                                      api_calls=max(int(cost.get('api_calls') or 0), len(calls))))
    evaluation_usage = combine_usage(scoring_parts)
    aggregate = combine_usage([frontend_usage, evaluation_usage])
    return dict(
        generation_priority=task['generation_priority'], episode_id=task['episode_id'],
        model_id=task['model_id'], model_name=task['model_name'], variant=task['variant'],
        scores=dict(v_l=scores.get('v_l'), v_v_within=vv.get('within_shot'),
                    v_v_cross=vv.get('cross_shot'), v_v_mean=vv.get('overall'),
                    **({'v_v_unintentional': scores.get('v_v_unintentional'),
                        'v_v_unintentional_or_uncertain': scores.get('v_v_unintentional_or_uncertain'),
                        'v_v_remainder': scores.get('v_v_remainder')} if chain == 'branch' else {})),
        issue_counts=scoring.get('counts'),
        **({'v_v_issue_statistics': scoring.get('v_v_issue_statistics')} if chain == 'branch' else {}),
        stage_token_costs=stage_costs,
        frontend_token_usage=frontend_usage, evaluation_token_usage=evaluation_usage,
        total_token_usage_and_cost=aggregate,
        output_dir=str(output), scoring_result=str(output / 'episode_scoring/result.json'),
        scoring_protocol=scoring.get('protocol'), model=scoring.get('model'), reasoning=scoring.get('reasoning'),
    )


def rebuild_final(root, tasks, progress):
    (root / 'episodes').mkdir(parents=True, exist_ok=True)
    rows = []
    for task in tasks:
        state = progress['tasks'].get(safe_id(task), {})
        if state.get('status') != 'success' or not valid_success(
                state, progress.get('expected_scoring_protocol', SCORING_PROTOCOLS[LEGACY_DISCOVERY_PROTOCOL])):
            continue
        rows.append(score_record(task, Path(state['output_dir'])))
    rows.sort(key=lambda r: (r['generation_priority'], MODEL_ORDER.index(r['model_id'])))
    jsonl = root / 'final_scores.jsonl'
    temp = jsonl.with_suffix('.jsonl.tmp')
    with temp.open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(temp, jsonl)
    csv_path = root / 'final_scores.csv'
    csv_temp = csv_path.with_suffix('.csv.tmp')
    fields = ['generation_priority', 'episode_id', 'model_id', 'model_name', 'variant',
              'v_l', 'v_v_within', 'v_v_cross', 'v_v_mean', 'api_calls', 'uncached_input_tokens',
              'cached_input_tokens', 'output_tokens', 'estimated_usd', 'scoring_result']
    with csv_temp.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            usage = row['total_token_usage_and_cost'] or {}
            writer.writerow(dict(
                generation_priority=row['generation_priority'], episode_id=row['episode_id'],
                model_id=row['model_id'], model_name=row['model_name'], variant=row['variant'],
                v_l=row['scores']['v_l'], v_v_within=row['scores']['v_v_within'],
                v_v_cross=row['scores']['v_v_cross'], v_v_mean=row['scores']['v_v_mean'],
                api_calls=usage.get('api_calls'),
                uncached_input_tokens=usage.get('uncached_input_tokens'),
                cached_input_tokens=usage.get('cached_input_tokens'), output_tokens=usage.get('output_tokens'),
                estimated_usd=usage.get('estimated_usd'), scoring_result=row['scoring_result']))
    os.replace(csv_temp, csv_path)
    complete = []
    for priority in sorted({t['generation_priority'] for t in tasks}):
        group = [t for t in tasks if t['generation_priority'] == priority]
        if all(progress['tasks'].get(safe_id(t), {}).get('status') == 'success' for t in group):
            complete.append(priority)
            episode = dict(generation_priority=priority, episode_id=group[0]['episode_id'],
                           model_results=[next(r for r in rows if r['generation_priority'] == priority and r['model_id'] == t['model_id']) for t in group])
            atomic_json(root / 'episodes' / f'priority_{priority:03d}.json', episode)
    progress['completed_tasks'] = len(rows)
    progress['completed_episode_count'] = len(complete)
    progress['last_completed_priority'] = max(complete, default=0)
    progress['updated_at_utc'] = now()
    atomic_json(root / 'progress.json', progress)
    return rows, complete


def signal_handler(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main():
    global STOP_REQUESTED
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True, help='Directory containing worklist.jsonl')
    parser.add_argument('--exp-dir', type=Path, help='Output directory for this experiment run (e.g. experiments/exp1). Defaults to batch.parent.')
    parser.add_argument('--exp-id', type=str, help='Experiment run identifier to append under exp-dir (e.g. exp1)')
    parser.add_argument('--gpu', action='append', required=True, metavar='INDEX=GPU-UUID',
                        help='Checked physical rocm-smi index and matching UUID; one per available card')
    parser.add_argument('--max-workers', type=int, default=5, help='At most one full model pipeline per active episode task')
    parser.add_argument('--shot-workers', type=int, default=2, help='Per-case isolated shot-review concurrency')
    parser.add_argument('--min-priority', type=int, help='Skip episodes below this generation_priority (for a second controller on a disjoint range)')
    parser.add_argument('--stop-after-priority', type=int, help='Finish this priority group and exit (for live smoke review)')
    parser.add_argument('--discovery-protocol', choices=sorted(REVIEW_PROTOCOLS),
                        help='Evaluator chain: v1 = historical (discovery v1 -> review v1 -> scoring v2); '
                             'v2 = checklist, multi-label issues; v3 = checklist, one label per issue; v4 = v3 + episode-wide '
                             'entity descriptions (v2-v4 -> review v5 -> scoring v3 by default); v5 = separate V-L / V-V '
                             'branches (-> review v6 -> scoring v5). Required for a new '
                             '--exp-dir; an existing one keeps its recorded chain (legacy directories are v1).')
    parser.add_argument('--review-protocol', choices=sorted(SCORING_PROTOCOLS),
                        help='For discovery v5: v6 (separate V-L / V-V reviews, scoring v5). For discovery v2-v4: v5 '
                             '(default for a new --exp-dir; core-problem verdicts with episode-wide '
                             'entity descriptions), v4 (core-problem verdicts) or v2 (previous per-label review); all are '
                             'scored with scoring v3. An existing '
                             'directory keeps its recorded review protocol (directories recorded before 2026-10-06 use '
                             'v2 for discovery v2).')
    args = parser.parse_args()
    batch = args.batch.resolve()
    base_root = args.exp_dir.resolve() if args.exp_dir else batch.parent
    root = (base_root / args.exp_id).resolve() if args.exp_id else base_root
    tasks = [json.loads(line) for line in (batch / 'worklist.jsonl').read_text().splitlines() if line.strip()]
    gpu_map = []
    for item in args.gpu:
        index, uuid = item.split('=', 1)
        gpu_map.append((int(index), uuid))
    if len({idx for idx, _ in gpu_map}) != len(gpu_map) or len(gpu_map) < args.max_workers:
        raise ValueError('Need a distinct checked GPU for every concurrent worker')
    if args.max_workers < 1 or args.max_workers > len(MODEL_ORDER):
        raise ValueError('At most five model results can run for the current episode')
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run this controller inside the existing approved Slurm allocation')

    progress_path = root / 'progress.json'
    events_path = root / 'events.jsonl'
    if progress_path.exists():
        progress = read(progress_path)
        if progress.get('cohort_protocol') != 'vl_vv_first200_multimodel_v1':
            raise ValueError('Progress file belongs to a different cohort')
        protocol = resolve_discovery_protocol(progress, args.discovery_protocol)
        review_protocol = resolve_review_protocol(progress, protocol, args.review_protocol)
        for state in progress.get('tasks', {}).values():
            if state.get('status') == 'running':
                state['status'] = 'interrupted'
                state['ended_at_utc'] = now()
                event(events_path, 'orphaned_task_on_resume', task_id=state.get('task_id'))
    else:
        protocol = resolve_discovery_protocol(None, args.discovery_protocol)
        review_protocol = resolve_review_protocol(None, protocol, args.review_protocol)
        progress = dict(cohort_protocol='vl_vv_first200_multimodel_v1', status='running',
                        slurm_job_id=os.environ['SLURM_JOB_ID'], started_at_utc=now(),
                        episode_order='generation_priority ascending; all five models complete before next episode',
                        model_order=MODEL_ORDER, gpu_map=[dict(index=i, uuid=u) for i, u in gpu_map],
                        tasks={}, completed_tasks=0, completed_episode_count=0, last_completed_priority=0)
    scoring_protocol = SCORING_PROTOCOLS[review_protocol]
    progress['discovery_protocol'] = protocol
    progress['review_protocol'] = review_protocol
    progress['expected_scoring_protocol'] = scoring_protocol
    progress['status'] = 'running'
    progress['slurm_job_id'] = os.environ['SLURM_JOB_ID']
    progress['gpu_map'] = [dict(index=i, uuid=u) for i, u in gpu_map]
    atomic_json(progress_path, progress)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    py = VACE_PYTHON
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false')
    env['EECBENCH_REVIEW_PYTHON'] = REVIEW_PYTHON
    episodes = sorted({t['generation_priority'] for t in tasks})
    event(events_path, 'batch_controller_started', slurm_job_id=os.environ['SLURM_JOB_ID'],
          max_workers=args.max_workers, python=VACE_PYTHON, shot_workers=args.shot_workers,
          discovery_protocol=protocol, review_protocol=review_protocol, expected_scoring_protocol=scoring_protocol)
    for priority in episodes:
        if args.min_priority is not None and priority < args.min_priority:
            continue
        if args.stop_after_priority is not None and priority > args.stop_after_priority:
            break
        group = [t for t in tasks if t['generation_priority'] == priority]
        if all(progress['tasks'].get(safe_id(t), {}).get('status') == 'success'
               and valid_success(progress['tasks'][safe_id(t)], scoring_protocol) for t in group):
            continue
        episode_id = group[0]['episode_id']
        event(events_path, 'episode_started', generation_priority=priority, episode_id=episode_id)
        active = []
        for worker_index, task in enumerate(group):
            if progress['tasks'].get(safe_id(task), {}).get('status') == 'success' and valid_success(progress['tasks'][safe_id(task)], scoring_protocol):
                continue
            if worker_index >= args.max_workers:
                raise RuntimeError('More tasks than workers for one episode; do not advance out of order')
            attempt = attempt_number(root, task)
            work, case, output = task_dirs(root, task, attempt)
            work.parent.mkdir(parents=True, exist_ok=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            prep_log = work.parent / f'prepare_attempt_{attempt:02d}.log'
            state = dict(task_id=safe_id(task), generation_priority=priority, episode_id=episode_id,
                         model_id=task['model_id'], model_name=task['model_name'], variant=task['variant'],
                         status='preparing', attempt=attempt, work_dir=str(work), case_dir=str(case),
                         output_dir=str(output), started_at_utc=now())
            progress['tasks'][safe_id(task)] = state
            atomic_json(progress_path, progress)
            event(events_path, 'task_preparation_started', task_id=safe_id(task), attempt=attempt)
            task_file = work.parent / f'{safe_id(task)}_attempt_{attempt:02d}.json'
            task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2) + '\n')
            prep = subprocess.run([PREPARE_PYTHON, str(PREPARE), '--task', str(task_file),
                                   '--work-root', str(work), '--task-id', safe_id(task)],
                                  stdout=prep_log.open('w'), stderr=subprocess.STDOUT, env=env)
            if prep.returncode:
                state.update(status='failed_prepare', ended_at_utc=now(), exit_code=prep.returncode,
                             log=str(prep_log))
                atomic_json(progress_path, progress)
                event(events_path, 'task_preparation_failed', task_id=safe_id(task), attempt=attempt, exit_code=prep.returncode)
                raise RuntimeError(f'Preparation failed for {safe_id(task)}; see {prep_log}')
            state['status'] = 'prepared'
            atomic_json(progress_path, progress)

        # Inputs are prepared in manifest order. Run available model full-pipelines
        # concurrently on unique physical cards, then wait for every model.
        for task in group:
            state = progress['tasks'].get(safe_id(task), {})
            if state.get('status') == 'success' and valid_success(state, scoring_protocol):
                continue
            work = Path(state['work_dir'])
            case = Path(state['case_dir'])
            output = Path(state['output_dir'])
            worker_index = group.index(task)
            gpu_index, gpu_uuid = gpu_map[worker_index]
            log = output.parent / f'{task["model_id"]}_attempt_{state["attempt"]:02d}_pipeline.log'
            command = [str(API), py, str(PIPELINE), '--case', str(case), '--output', str(output),
                       '--mode', 'full', '--gpu', str(gpu_index), '--gpu-uuid', gpu_uuid,
                       '--shot-workers', str(args.shot_workers), '--gpu-python', GPU_PYTHON,
                       '--discovery-protocol', protocol, '--review-protocol', review_protocol]
            stream = log.open('w')
            proc = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=env,
                                    start_new_session=True)
            state.update(status='running', gpu_index=gpu_index, gpu_uuid=gpu_uuid,
                         pipeline_log=str(log), pid=proc.pid, process_started_at_utc=now())
            progress['tasks'][safe_id(task)] = state
            active.append((task, proc, stream, state))
            event(events_path, 'full_pipeline_started', task_id=safe_id(task), attempt=state['attempt'],
                  gpu_index=gpu_index, gpu_uuid=gpu_uuid, pid=proc.pid)
        atomic_json(progress_path, progress)

        while active:
            if STOP_REQUESTED:
                for task, proc, stream, state in active:
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                for task, proc, stream, state in active:
                    proc.wait(timeout=90)
                    stream.close()
                    state.update(status='interrupted', ended_at_utc=now(), exit_code=proc.returncode)
                    progress['tasks'][safe_id(task)] = state
                atomic_json(progress_path, progress)
                progress['status'] = 'interrupted'
                atomic_json(progress_path, progress)
                event(events_path, 'batch_controller_interrupted', generation_priority=priority)
                return 143
            remaining = []
            for task, proc, stream, state in active:
                code = proc.poll()
                if code is None:
                    remaining.append((task, proc, stream, state))
                    continue
                stream.close()
                if code == 0 and valid_success(state, scoring_protocol):
                    state.update(status='success', ended_at_utc=now(), exit_code=0)
                    event(events_path, 'full_pipeline_success', task_id=safe_id(task), attempt=state['attempt'])
                else:
                    state.update(status='failed_pipeline', ended_at_utc=now(), exit_code=code)
                    progress['tasks'][safe_id(task)] = state
                    atomic_json(progress_path, progress)
                    event(events_path, 'full_pipeline_failed', task_id=safe_id(task), attempt=state['attempt'], exit_code=code)
                    for other_task, other_proc, other_stream, other_state in active:
                        if other_proc is proc or other_proc.poll() is not None:
                            continue
                        try:
                            os.killpg(other_proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    for other_task, other_proc, other_stream, other_state in active:
                        if other_proc is proc:
                            continue
                        other_proc.wait()
                        other_stream.close()
                        if other_state.get('status') == 'running':
                            other_state.update(status='interrupted', ended_at_utc=now(), exit_code=other_proc.returncode)
                            progress['tasks'][safe_id(other_task)] = other_state
                    atomic_json(progress_path, progress)
                    raise RuntimeError(f'Pipeline failed for {safe_id(task)}; see {state["pipeline_log"]}')
                progress['tasks'][safe_id(task)] = state
                rows, complete = rebuild_final(root, tasks, progress)
            active = remaining
            if active:
                time.sleep(3)
        rows, complete = rebuild_final(root, tasks, progress)
        if not all(progress['tasks'].get(safe_id(t), {}).get('status') == 'success' for t in group):
            raise RuntimeError(f'Priority {priority} did not finish all five models')
        event(events_path, 'episode_completed', generation_priority=priority, episode_id=episode_id,
              model_count=len(group), score_count=len(rows))
        if STOP_REQUESTED:
            progress['status'] = 'interrupted'
            atomic_json(progress_path, progress)
            return 143
        if args.stop_after_priority == priority:
            progress['status'] = 'smoke_group_complete'
            progress['smoke_group_priority'] = priority
            atomic_json(progress_path, progress)
            event(events_path, 'batch_stopped_after_smoke_group', generation_priority=priority)
            return 0

    rows, complete = rebuild_final(root, tasks, progress)
    if len(complete) == 200 and len(rows) == 1000:
        progress['status'] = 'complete'
        progress['completed_at_utc'] = now()
        event(events_path, 'batch_completed', episode_count=200, task_count=1000)
    else:
        progress['status'] = 'partial'
        event(events_path, 'batch_checkpointed', completed_episodes=len(complete), completed_tasks=len(rows))
    atomic_json(progress_path, progress)
    print(f'Batch status: {progress["status"]}; {len(complete)}/200 episodes; {len(rows)}/1000 model scores', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        progress_path = Path(__file__).resolve().parent / 'progress.json'
        if progress_path.is_file():
            progress = read(progress_path)
            progress.update(status='failed', failed_at_utc=now(), failure=str(exc))
            atomic_json(progress_path, progress)
            event(Path(__file__).resolve().parent / 'events.jsonl', 'batch_controller_failed',
                  failure=str(exc))
        raise
