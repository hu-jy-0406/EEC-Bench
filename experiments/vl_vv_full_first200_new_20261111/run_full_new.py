#!/usr/bin/env python3
"""Full first-200 run (1,000 videos) of the new default pipeline without and with the unspecified plug-in (owner,
2026-11-11: "复用V-L打分，然后对new和new+插件跑200个全量"). Worn items and place parts are entities, contracts 1-200 of
the granularity pass, pipeline C as default, OpenRouter transport.

Code: code/EECBench, a frozen copy of the live configs, prompts, schemas, scripts, skills and tests at 2026-11-11 20:01
Dubai (SHA256SUMS_code_frozen); data, models and experiments are links to the live tree.

Per video (the 1,000 successful videos of ../vl_vv_full_first200_v3_20261109; their v3 cases are read-only sources):
  prepare     a fresh case from the v3 case's keyframe manifest and the episode's current contract with its compiled
              requirement package; the v3 case's WeDetect run of the same keyframes is copied in (detector and
              keyframes unchanged, every model judgment runs fresh);
  pipeline    run_vl_vv_pipeline.py --mode full --reuse-detections (plug-in off) -> results/  = new;
  plugin, with_vv_review
              the plug-in on results/vv_detection and one V-V review of the merged candidates -> results_with/;
  with_episode_scoring
              scoring with results/vl_review and the merged V-V review, reusing the V-L severities of
              results/episode_scoring (--vl-scoring-from; no second V-L severity call, so new and new + plug-in report
              the same V-L score) -> results_with/episode_scoring  = new + plug-in.
The 40 videos of ../vl_vv_entity_scope_validation_20261111 (same pipeline; code differs from the snapshot only in the
cut-off-reply transport fix and the --vl-scoring-from option) are reused: only with_episode_scoring runs here, on the
validation folder's reviews, into runs/<task>/results_with/episode_scoring (runs/<task>/reused_from.json).

Each video holds one checked GPU slot (--gpu INDEX=UUID) for its whole pipeline (the pipeline's GPU guard needs an
otherwise empty GPU). Several drivers share the task list through claims/; a file stop_<host> makes that host's driver
start no new video. Budget gate on the standard-price estimate of this run's calls. Run inside an owned Slurm
allocation."""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent
CODE = EXP / 'code' / 'EECBench'
SCRIPTS = CODE / 'scripts'
LIVE = EXP.parents[1]
V3 = LIVE / 'experiments' / 'vl_vv_full_first200_v3_20261109'
VALID = LIVE / 'experiments' / 'vl_vv_entity_scope_validation_20261111'
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
PRICE = (0.10, 0.01, 0.50)
LOCK = threading.Lock()
# API loader; --provider openai (owner, 2026-11-12: "Rerun via OpenAI" for videos blocked by OpenRouter's input
# moderation) uses openai_api_env.sh, direct OpenAI with the same model and request.
LOADER = ['openrouter_env.sh', 'openrouter']
sys.path.insert(0, str(SCRIPTS))
import episode_contract as contract_io  # noqa: E402


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')


# One event log per driver (events/<host>_<job>.jsonl): drivers on several hosts appending to one shared file garbled
# a line on 2026-11-11; events.jsonl keeps the events written before that.
EVENTS = [EXP / 'events.jsonl']


def log(**row):
    with LOCK, open(EVENTS[0], 'a') as h:
        h.write(json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S'), **row), ensure_ascii=False) + '\n')


def spent(root):
    total = 0.0
    for st in Path(root).rglob('status.json'):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        for u in s.get('usage') or s.get('known_usage') or []:
            i, c, o = int(u.get('input_tokens') or 0), int(u.get('cached_input_tokens') or 0), int(u.get('output_tokens') or 0)
            total += ((i - c) * PRICE[0] + c * PRICE[1] + o * PRICE[2]) / 1e6
    return total


FINISHED = {}  # task -> standard USD of a video whose driver job has ended (counted once, not rescanned)


def spent_run():
    total = 0.0
    for folder in (EXP / 'runs').iterdir() if (EXP / 'runs').is_dir() else []:
        if folder.name not in FINISHED:
            usd = spent(folder)
            if (folder / 'stages' / 'with_episode_scoring.done').is_file():
                FINISHED[folder.name] = usd
            total += usd
        else:
            total += FINISHED[folder.name]
    return total


_TIME_LEFT = {}


def allocation_seconds_left(job_id):
    """Seconds left in this Slurm allocation (squeue %L), refreshed at most once a minute; unknown = no limit."""
    with LOCK:
        cached = _TIME_LEFT.get('value')
        if cached is not None and time.time() - _TIME_LEFT['at'] < 60:
            return cached - (time.time() - _TIME_LEFT['at'])
        text = subprocess.run(['squeue', '-h', '-j', job_id, '-o', '%L'], capture_output=True, text=True).stdout.strip()
        try:
            days, _, clock = text.rpartition('-')
            parts = [int(x) for x in clock.split(':')]
            while len(parts) < 3:
                parts.insert(0, 0)
            value = int(days or 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]
        except ValueError:  # UNLIMITED, NOT_SET or a failed query
            value = float('inf')
        _TIME_LEFT.update(value=value, at=time.time())
        return value


def sources():
    out = {}
    for path in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in read(path)['tasks'].items():
            if t.get('status') == 'success':
                out[tid] = Path(t['case_dir']).resolve()
    return out


def run(base, name, cmd, env_extra=None):
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false', EECBENCH_REVIEW_PYTHON=VACE,
               EECBENCH_API_MODEL='gpt-6-luna', EECBENCH_API_PROVIDER=LOADER[1], **(env_extra or {}))
    start = time.time()
    (base / 'logs').mkdir(parents=True, exist_ok=True)
    with open(base / 'logs' / f'{name}.log', 'w') as h:
        rc = subprocess.call([str(SCRIPTS / LOADER[0]), *map(str, cmd)], stdout=h, stderr=subprocess.STDOUT,
                             cwd=str(CODE), env=env)
    log(event=name, task=base.name, exit_code=rc, seconds=round(time.time() - start, 1))
    return rc


def done(base, name):
    return (base / 'stages' / f'{name}.done').is_file()


def mark(base, name):
    write(base / 'stages' / f'{name}.done', dict(time=time.strftime('%Y-%m-%dT%H:%M:%S')))


CPU = dict(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')


def scoring_cmd(vl_review, vv_review, output, vl_scoring_from):
    return [VACE, SCRIPTS / 'run_vl_vv_branch_scoring.py', '--vl-review', vl_review, '--vv-review', vv_review,
            '--output', output, '--chain', 'v6', '--vl-scoring-from', vl_scoring_from]


def reused_video(task):
    """A validation video: only the plug-in scoring with the reused V-L severities runs here."""
    base, src = EXP / 'runs' / task, VALID / 'runs' / task
    target = base / 'results_with' / 'episode_scoring'
    if not done(base, 'with_episode_scoring'):
        write(base / 'reused_from.json', dict(
            source=str(src), reused=['case', 'results (new)', 'results_with/vv_plugin', 'results_with/vv_review'],
            rule='validation video of the same pipeline; only the plug-in scoring runs here, with --vl-scoring-from'))
        if target.exists():
            shutil.rmtree(target)
        if run(base, 'with_episode_scoring', scoring_cmd(src / 'results/vl_review/result.json',
                                                         src / 'results_with/vv_review/result.json', target,
                                                         src / 'results/episode_scoring'), CPU):
            return 'failed at with_episode_scoring'
        mark(base, 'with_episode_scoring')
    return 'success'


def video(task, src_case, gpus):
    base = EXP / 'runs' / task
    case, out, out_w = base / 'case', base / 'results', base / 'results_with'
    if not done(base, 'prepare'):
        if case.exists():
            shutil.rmtree(case)
        episode = read(src_case / 'raw_manifest.json')['episode_id']
        contract = contract_io.resolve_v2_contract(episode)
        compiled = contract_io.resolve_compiled(episode, contract)
        if run(base, 'prepare', [VACE, SCRIPTS / 'run_vl_vv_detection.py', 'prepare', '--manifest', src_case / 'raw_manifest.json',
                                 '--contract', contract, '--case', case, '--compiled', compiled]):
            return 'failed at prepare'
        shutil.copy(src_case / 'benchmark_metadata.json', case / 'benchmark_metadata.json')
        shutil.copytree(src_case / 'entities' / 'detections', case / 'wedetect_reused')
        mark(base, 'prepare')
    if not done(base, 'pipeline'):
        if out.exists():  # the pipeline needs a fresh output folder; an interrupted case starts again from prepare
            raise RuntimeError(f'{task}: interrupted pipeline; move {base} aside to rerun')
        gpu = gpus.get()
        try:
            rc = run(base, 'pipeline', [VACE, SCRIPTS / 'run_vl_vv_pipeline.py', '--case', case, '--output', out, '--mode', 'full',
                                        '--gpu', gpu[0], '--gpu-uuid', gpu[1], '--gpu-python', VACE, '--shot-workers', '3',
                                        '--reuse-detections', case / 'wedetect_reused'])
        finally:
            gpus.put(gpu)
        if rc:
            return 'failed at pipeline'
        mark(base, 'pipeline')
    for name, cmd in [
            ('plugin', [VACE, SCRIPTS / 'run_vl_vv_unspecified_plugin.py', '--case', case, '--detection',
                        out / 'vv_detection/result.json', '--output', out_w / 'vv_plugin']),
            ('with_vv_review', [VACE, SCRIPTS / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection',
                                out_w / 'vv_plugin/result.json', '--output', out_w / 'vv_review', '--chain', 'v6']),
            ('with_episode_scoring', scoring_cmd(out / 'vl_review/result.json', out_w / 'vv_review/result.json',
                                                 out_w / 'episode_scoring', out / 'episode_scoring'))]:
        if done(base, name):
            continue
        target = {'plugin': out_w / 'vv_plugin', 'with_vv_review': out_w / 'vv_review',
                  'with_episode_scoring': out_w / 'episode_scoring'}[name]
        if target.exists():  # an interrupted stage starts again
            shutil.rmtree(target)
        if run(base, name, cmd, CPU):
            return f'failed at {name}'
        mark(base, name)
    return 'success'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--gpu', action='append', default=[], metavar='INDEX=UUID')
    p.add_argument('--only', nargs='*')
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--cap', type=float, default=140.0, help='Standard-price USD cap of this run (not a bill)')
    p.add_argument('--slots-per-gpu', type=int, default=1,
                   help='Videos sharing one GPU (owner, 2026-11-11 "应用提速"); above 1 every GPU subprocess holds a '
                        'per-GPU flock (EECBENCH_GPU_LOCK_DIR) so only one of them uses the GPU at a time')
    p.add_argument('--min-time-left', type=int, default=1800,
                   help='Start no new video when the allocation has fewer seconds left (a video takes about 10 min)')
    p.add_argument('--provider', choices=('openrouter', 'openai'), default='openrouter')
    a = p.parse_args()
    LOADER[:] = ['openrouter_env.sh', 'openrouter'] if a.provider == 'openrouter' else ['openai_api_env.sh', 'openai']
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside an owned Slurm allocation')
    gpus = queue.Queue()
    for _ in range(a.slots_per_gpu):  # slots of different GPUs alternate in the queue
        for g in a.gpu:
            gpus.put(tuple(g.split('=', 1)))
    if a.slots_per_gpu > 1:
        os.environ['EECBENCH_GPU_LOCK_DIR'] = '/tmp/eecbench_gpu_locks'
    if gpus.empty():
        raise SystemExit('--gpu INDEX=UUID required')
    src = sources()
    reused = {t for t in src if (VALID / 'runs' / t / 'stages' / 'with_episode_scoring.done').is_file()}
    tasks = sorted(src)  # priority order, the five models interleaved
    tasks = [t for t in tasks if not a.only or t in a.only]
    host = os.uname().nodename
    (EXP / 'events').mkdir(exist_ok=True)
    EVENTS[0] = EXP / 'events' / f"{host}_{os.environ['SLURM_JOB_ID']}.jsonl"
    log(event='driver_started', provider=a.provider, tasks=len(tasks), reused=len(reused & set(tasks)), gpus=a.gpu, host=host,
        slurm=os.environ['SLURM_JOB_ID'], cap=a.cap, threads=a.threads, slots_per_gpu=a.slots_per_gpu,
        gpu_lock_dir=os.environ.get('EECBENCH_GPU_LOCK_DIR'))
    reserved = {}
    (EXP / 'claims').mkdir(exist_ok=True)

    job_id = os.environ['SLURM_JOB_ID']

    def job(t):
        if (EXP / f'stop_{host}').exists():
            return t, 'not started: stop requested'
        if allocation_seconds_left(job_id) < a.min_time_left:
            return t, 'not started: allocation ending'
        claim = EXP / 'claims' / t
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f'{host} {job_id} {os.getpid()}'.encode())
            os.close(fd)
        except FileExistsError:
            if (EXP / 'runs' / t / 'stages' / 'with_episode_scoring.done').is_file():
                return t, 'done'
            owner = claim.read_text().split()
            # a claim of this host and allocation is resumed (driver restarted); claims written before
            # 2026-11-11 21:00 Dubai hold only "host pid"
            if owner[0] != host or (len(owner) >= 3 and owner[1] != job_id):
                return t, 'claimed elsewhere'
        with LOCK:
            if spent_run() + sum(reserved.values()) + 0.2 > a.cap:
                return t, 'not started: budget gate'
            reserved[t] = 0.2
        try:
            log(event='start', task=t, reused=t in reused)
            try:
                r = reused_video(t) if t in reused else video(t, src[t], gpus)
            except Exception as exc:  # noqa: BLE001 - record and continue
                r = f'failed: {type(exc).__name__}: {exc}'[:400]
            log(event='result', task=t, result=r)
            with LOCK:
                FINISHED[t] = spent(EXP / 'runs' / t)
            return t, r
        finally:
            with LOCK:
                reserved.pop(t, None)
    with ThreadPoolExecutor(a.threads) as pool:
        for t, r in pool.map(job, tasks):
            print(t, r, flush=True)
    log(event='driver_finished', spent_usd=round(spent_run(), 4))


if __name__ == '__main__':
    main()
