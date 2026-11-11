#!/usr/bin/env python3
"""Full first-200 evaluation, third version (2026-11-09): chain v6 with V-V detection one call per checklist item
(owner choice, live since 15:31 Dubai) and the owner-approved rule that walls, floors, ceilings and the ground are part
of their place; GPT-6 Luna, reasoning low.  Copied from vl_vv_full_first200_v2_20261109/run_full.py (itself from
vl_vv_full_first200_20261107); only this docstring differs.

--tasks full runs the whole pipeline (prepare, frontend, both branches, scoring) for the videos that the stopped
first run (--reuse-from, default vl_vv_full_first200_20261107) did not finish.  --tasks reuse takes a video that the
first run finished, keeps its frontend case and its V-L detection and review unchanged (links to the first run; the
frontend and the V-L branch did not change), and reruns only V-V detection, V-V review and episode scoring with the
current code.  Its results/run.json records mode reuse_vv and the source attempt.

Several controllers (CPU controllers on different nodes, later GPU controllers) can work on the same
worklist at the same time, each with its own --run.  A worker claims a task by creating runs/claims/<task>.json
exclusively; a task that succeeded in any run, or that another worker has claimed, is skipped.  A failed task
releases its claim, so any controller may retry it, until it has failed MAX_ATTEMPTS times.  Creating the file
runs/<run>/DRAIN makes that controller's workers finish their current task and stop.  --release-claims-of RUN
removes the open claims of a controller that has died (check first that it is no longer running).
--shard K/N additionally restricts a controller to the tasks whose sorted index is K modulo N.

One worker per checked GPU; each worker prepares a fresh case for its next task
(the batch's prepare_case.py: contract v2, recorded-cut keyframes) and runs
run_vl_vv_pipeline.py --mode full on its own GPU.  With --cpu, --workers CPU
workers run the frontend with --frontend-device cpu (WeDetect and Grounding DINO
on CPU, no GPU visible, DINO deferred); everything else is the same.  Unlike the first-200 batch
controller, tasks are not grouped by episode, so four GPUs serve five models.
A run directory keeps progress.json and events.jsonl; a rerun skips tasks that
already succeeded and gives failed tasks a new attempt directory.
"""
import argparse
import json
import os
import queue
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parent
PREPARE = ROOT / 'EECBench/experiments/vl_vv_multimodel_first200_20260926/prepare_case.py'
PIPELINE = ROOT / 'EECBench/scripts/run_vl_vv_pipeline.py'
API = ROOT / 'EECBench/scripts/openai_api_env.sh'
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
SCORING_PROTOCOL = 'vl_vv_episode_scoring_v6'
CLAIMS = EXP / 'runs/claims'
ATTEMPTS = EXP / 'runs/attempts'
MAX_ATTEMPTS = 2
FIRST_RUN = ROOT / 'EECBench/experiments/vl_vv_full_first200_20261107'
SCRIPTS = ROOT / 'EECBench/scripts'
REUSE_STAGES = ('vv_detection', 'vv_review', 'episode_scoring')
LOCK = threading.Lock()
CHILDREN = set()
STOP = threading.Event()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def task_id(task):
    return f'priority_{task["generation_priority"]:03d}__{task["model_id"]}'


def succeeded(output):
    try:
        run, score = read(output / 'run.json'), read(output / 'episode_scoring/result.json')
        return run.get('status') == 'success' and score.get('status') == 'success' and \
            score.get('protocol') == SCORING_PROTOCOL
    except (OSError, ValueError, KeyError):
        return False


class Run:
    def __init__(self, root):
        self.root = root
        self.progress_path = root / 'progress.json'
        self.events = root / 'events.jsonl'
        self.progress = read(self.progress_path) if self.progress_path.exists() else dict(tasks={}, started=now())

    def event(self, kind, **fields):
        with LOCK, self.events.open('a') as stream:
            stream.write(json.dumps(dict(time=now(), event=kind, **fields), ensure_ascii=False) + '\n')

    def update(self, tid, **fields):
        with LOCK:
            self.progress['tasks'].setdefault(tid, {}).update(fields)
            atomic(self.progress_path, self.progress)


def attempt_dirs(root, task):
    base = root / task['model_id'] / f'priority_{task["generation_priority"]:03d}_{task["episode_id"]}'
    previous = [int(p.name.split('_')[-1]) for p in base.glob('attempt_*')] if base.exists() else []
    attempt = max(previous, default=0) + 1
    task_base = base / f'attempt_{attempt:02d}'
    return attempt, task_base / 'work', task_base / 'work/case', task_base / 'results'


def run_child(command, log, env):
    with log.open('w') as stream:
        proc = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        with LOCK:
            CHILDREN.add(proc)
        try:
            return proc.wait()
        finally:
            with LOCK:
                CHILDREN.discard(proc)


def done_elsewhere(tid):
    """True if any run under runs/ has a verified success for this task."""
    for path in (EXP / 'runs').glob('*/progress.json'):
        try:
            state = read(path)['tasks'].get(tid, {})
        except (OSError, ValueError, KeyError):
            continue
        if state.get('status') == 'success' and succeeded(Path(state['output_dir'])):
            return True
    return False


def failures(tid):
    path = ATTEMPTS / f'{tid}.jsonl'
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip() and json.loads(line)['status'] != 'success')


def claim(run, tid, worker_name):
    """Exclusive claim; False if another worker holds it or the task is finished or exhausted."""
    if done_elsewhere(tid) or failures(tid) >= MAX_ATTEMPTS:
        return False
    try:
        fd = os.open(CLAIMS / f'{tid}.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as stream:
        json.dump(dict(task_id=tid, run=run.root.name, worker=worker_name, host=os.uname().nodename,
                       pid=os.getpid(), status='running', claimed=now()), stream)
    return True


def finish_claim(run, tid, ok, attempt):
    with LOCK, (ATTEMPTS / f'{tid}.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(time=now(), run=run.root.name, attempt=attempt,
                                     status='success' if ok else 'failed')) + '\n')
    path = CLAIMS / f'{tid}.json'
    if ok:
        state = read(path)
        state.update(status='success', ended=now())
        atomic(path, state)
    else:
        path.unlink(missing_ok=True)


def claimable(rows):
    """Tasks no worker holds that have not succeeded and have attempts left (claims released by failures)."""
    return [row for row in rows if not (CLAIMS / f'{task_id(row)}.json').exists()
            and not done_elsewhere(task_id(row)) and failures(task_id(row)) < MAX_ATTEMPTS]


def first_run_successes(first_run):
    """{task_id: attempt dir} of the first run's verified successes."""
    found = {}
    for path in sorted((first_run / 'runs').glob('*/progress.json')):
        for tid, state in read(path)['tasks'].items():
            if state.get('status') == 'success' and succeeded(Path(state['output_dir'])):
                found[tid] = Path(state['output_dir']).parent
    return found


def reuse_one(run, tid, task, source, env):
    """V-V detection, V-V review and episode scoring with the current code on the first run's case and V-L review."""
    attempt, work, case, output = attempt_dirs(run.root, task)
    work.mkdir(parents=True)
    (work.parent / 'task.json').write_text(json.dumps(task, ensure_ascii=False, indent=2) + '\n')
    case.symlink_to(source / 'work/case', target_is_directory=True)
    output.mkdir()
    for name in ('vl_detection', 'vl_review'):
        (output / name).symlink_to(source / 'results' / name, target_is_directory=True)
    (output / 'logs').mkdir()
    state = dict(protocol='vl_vv_pipeline_v1', mode='reuse_vv', status='running', started=now(), case=str(case),
                 output=str(output), source_attempt=str(source), model='gpt-6-luna', reasoning='low',
                 discovery_protocol='v6', review_protocol='v7', scoring_protocol=SCORING_PROTOCOL,
                 reused=dict(frontend=str(source / 'work/case'), vl_detection=str(source / 'results/vl_detection'),
                             vl_review=str(source / 'results/vl_review')), stages=[])
    atomic(output / 'run.json', state)
    commands = dict(
        vv_detection=[SCRIPTS / 'run_vl_vv_branch_detection.py', '--branch', 'vv', '--case', case,
                      '--output', output / 'vv_detection', '--chain', 'v6'],
        vv_review=[SCRIPTS / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case,
                   '--detection', output / 'vv_detection/result.json', '--output', output / 'vv_review', '--chain', 'v6'],
        episode_scoring=[SCRIPTS / 'run_vl_vv_branch_scoring.py', '--vl-review', output / 'vl_review/result.json',
                         '--vv-review', output / 'vv_review/result.json', '--output', output / 'episode_scoring',
                         '--chain', 'v6'])
    run.update(tid, status='running', mode='reuse_vv', attempt=attempt, case_dir=str(case), output_dir=str(output),
               source_attempt=str(source), started=now())
    run.event('pipeline_started', task_id=tid, attempt=attempt, mode='reuse_vv')
    start, code = time.time(), 0
    for name in REUSE_STAGES:
        stage_start = time.time()
        command = [str(API), VACE, *map(str, commands[name])]
        code = run_child(command, output / 'logs' / f'{name}.log', env)
        state['stages'].append(dict(name=name, command=command, exit_code=code,
                                    seconds=round(time.time() - stage_start, 1)))
        if code:
            break
    state.update(status='success' if code == 0 else 'failed', seconds=round(time.time() - start, 1), ended=now(),
                 result_json=str(output / 'episode_scoring/result.json'))
    atomic(output / 'run.json', state)
    ok = code == 0 and succeeded(output)
    run.update(tid, status='success' if ok else 'failed_pipeline', exit_code=code, ended=now(),
               pipeline_seconds=round(time.time() - start, 1))
    run.event('pipeline_success' if ok else 'pipeline_failed', task_id=tid, attempt=attempt, exit_code=code)
    return ok, attempt


def worker(run, tasks, rows, gpu_index, gpu_uuid, shot_workers, env, worker_name, reuse=None):
    """gpu_index None: CPU frontend.  When the queue runs empty, tasks released by failed attempts of any
    controller are queued again; the worker stops when nothing is left to claim."""
    while not STOP.is_set():
        if (run.root / 'DRAIN').exists():
            run.event('worker_drained', worker=worker_name)
            return
        try:
            task = tasks.get_nowait()
        except queue.Empty:
            with LOCK:
                again = claimable(rows) if tasks.empty() else []
                for row in again:
                    tasks.put(row)
            if again or not tasks.empty():
                continue
            return
        tid = task_id(task)
        if not claim(run, tid, worker_name):
            continue
        if reuse is not None:
            ok, attempt = reuse_one(run, tid, task, reuse[tid], env)
            if STOP.is_set() and not ok:
                (CLAIMS / f'{tid}.json').unlink(missing_ok=True)
                continue
            finish_claim(run, tid, ok, attempt)
            continue
        attempt, work, case, output = attempt_dirs(run.root, task)
        work.parent.mkdir(parents=True)
        task_file = work.parent / 'task.json'
        task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2) + '\n')
        run.update(tid, status='preparing', attempt=attempt, case_dir=str(case), output_dir=str(output),
                   gpu_index=gpu_index, gpu_uuid=gpu_uuid, frontend_device='cpu' if gpu_index is None else 'cuda',
                   started=now())
        start = time.time()
        code = run_child([VACE, str(PREPARE), '--task', str(task_file), '--work-root', str(work), '--task-id', tid,
                          '--contract-format', 'v2'], work.parent / 'prepare.log', env)
        if code:
            run.update(tid, status='failed_prepare', exit_code=code, ended=now())
            run.event('prepare_failed', task_id=tid, attempt=attempt, exit_code=code)
            finish_claim(run, tid, False, attempt)
            continue
        run.update(tid, status='running', prepare_seconds=round(time.time() - start, 1))
        run.event('pipeline_started', task_id=tid, attempt=attempt, gpu_index=gpu_index)
        start = time.time()
        device = ['--frontend-device', 'cpu'] if gpu_index is None else \
            ['--gpu', str(gpu_index), '--gpu-uuid', gpu_uuid, '--gpu-python', VACE]
        code = run_child([str(API), VACE, str(PIPELINE), '--case', str(case), '--output', str(output),
                          '--mode', 'full', *device, '--shot-workers', str(shot_workers),
                          '--discovery-protocol', 'v6', '--review-protocol', 'v7'],
                         work.parent / 'pipeline.log', env)
        ok = code == 0 and succeeded(output)
        run.update(tid, status='success' if ok else 'failed_pipeline', exit_code=code, ended=now(),
                   pipeline_seconds=round(time.time() - start, 1))
        run.event('pipeline_success' if ok else 'pipeline_failed', task_id=tid, attempt=attempt, exit_code=code)
        if STOP.is_set() and not ok:
            # Stopped by a signal: release the claim without counting a failed attempt.
            (CLAIMS / f'{tid}.json').unlink(missing_ok=True)
            continue
        finish_claim(run, tid, ok, attempt)


def stop(*_):
    STOP.set()
    with LOCK:
        for proc in list(CHILDREN):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Run name under runs/')
    parser.add_argument('--worklist', type=Path,
                        default=ROOT / 'EECBench/experiments/vl_vv_multimodel_first200_20260926/batch/worklist.jsonl')
    parser.add_argument('--shard', default='0/1', help='K/N: run tasks whose sorted index is K modulo N')
    parser.add_argument('--gpu', action='append', default=[], metavar='INDEX=GPU-UUID')
    parser.add_argument('--cpu', action='store_true', help='CPU frontend, no GPU (DINO deferred)')
    parser.add_argument('--workers', type=int, default=2, help='Number of CPU workers with --cpu')
    parser.add_argument('--shot-workers', type=int, default=2)
    parser.add_argument('--only', nargs='*', help='Task IDs to run (default: all)')
    parser.add_argument('--tasks', choices=('full', 'reuse'), required=True,
                        help='full: videos the first run did not finish; reuse: videos it finished (V-V and scoring only)')
    parser.add_argument('--reuse-from', type=Path, default=FIRST_RUN, help='The stopped first run')
    parser.add_argument('--release-claims-of', metavar='RUN',
                        help='Remove the open (running) claims of RUN, a controller that has died, and exit')
    args = parser.parse_args()
    CLAIMS.mkdir(parents=True, exist_ok=True)
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    if args.release_claims_of:
        released = []
        for path in CLAIMS.glob('*.json'):
            state = read(path)
            if state.get('run') == args.release_claims_of and state.get('status') == 'running':
                path.unlink()
                released.append(state['task_id'])
        print(json.dumps(dict(released=sorted(released))))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside the Slurm allocation that owns the GPUs')
    if args.cpu == bool(args.gpu):
        raise ValueError('Give either --cpu or at least one --gpu')
    first = first_run_successes(args.reuse_from)
    running = [p.name for p in (args.reuse_from / 'runs/claims').glob('*.json') if read(p).get('status') == 'running']
    if running:
        raise RuntimeError(f'The first run still has running tasks {running[:5]}; wait until it has drained')
    gpus = [(int(item.split('=', 1)[0]), item.split('=', 1)[1]) for item in args.gpu]
    if len({index for index, _ in gpus}) != len(gpus):
        raise ValueError('Each worker needs a distinct GPU')
    slots = [(None, None)] * args.workers if args.cpu else gpus
    root = EXP / 'runs' / args.run
    root.mkdir(parents=True, exist_ok=True)
    run = Run(root)
    rows = [json.loads(line) for line in args.worklist.read_text().splitlines() if line.strip()]
    rows.sort(key=lambda row: (row['generation_priority'], row['model_id']))
    shard, shards = (int(x) for x in args.shard.split('/'))
    if not 0 <= shard < shards:
        raise ValueError('--shard must be K/N with 0 <= K < N')
    rows = [row for index, row in enumerate(rows) if index % shards == shard]
    if args.only:
        rows = [row for row in rows if task_id(row) in args.only]
    rows = [row for row in rows if (task_id(row) in first) == (args.tasks == 'reuse')]
    pending = queue.Queue()
    for row in rows:
        tid = task_id(row)
        if done_elsewhere(tid):
            continue
        pending.put(row)
    run.progress.update(slurm_job_id=os.environ['SLURM_JOB_ID'], gpus=[dict(index=i, uuid=u) for i, u in gpus],
                        frontend_device='cpu' if args.cpu else 'cuda', workers=len(slots),
                        chain='v6', model='gpt-6-luna', shard=args.shard, worklist=str(args.worklist),
                        task_set=args.tasks, reuse_from=str(args.reuse_from), first_run_successes=len(first),
                        host=os.uname().nodename, resumed=now())
    atomic(run.progress_path, run.progress)
    run.event('run_started', queued=pending.qsize(), gpus=len(gpus), workers=len(slots))
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false',
               EECBENCH_REVIEW_PYTHON=VACE)
    if args.cpu:
        env.update(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
    reuse = first if args.tasks == 'reuse' else None
    threads = [threading.Thread(target=worker, args=(run, pending, rows, index, uuid, args.shot_workers, env,
                                                     f'{args.run}:{"cpu" if index is None else "gpu"}{n}', reuse))
               for n, (index, uuid) in enumerate(slots)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    states = [state['status'] for state in run.progress['tasks'].values()]
    run.event('run_finished', success=states.count('success'), total=len(states))


if __name__ == '__main__':
    main()
