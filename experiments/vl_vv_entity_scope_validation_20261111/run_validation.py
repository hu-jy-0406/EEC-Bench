#!/usr/bin/env python3
"""Validation of the new default pipeline on the 40-video sample (owner, 2026-11-11: worn items and place parts are
entities; pipeline C default; the unspecified branch as a plug-in).

Per video (the 40 tasks of ../vl_vv_full_first200_v3_20261109/sample_task_ids.txt, 8 per model):
  prepare     a fresh case from the v3 case's keyframe manifest and the episode's current contract (granularity pass
              of 2026-11-11) with its recompiled requirement package (run_vl_vv_detection.py prepare); the v3 case's
              WeDetect run of the same keyframes is copied into the case (owner: reuse earlier detection results where
              the logic allows; detector and keyframes are unchanged, every model judgment runs fresh);
  pipeline    run_vl_vv_pipeline.py --mode full --reuse-detections (live code: background frontend on, plug-in off)
              -> results/;
  plug-in     run_vl_vv_unspecified_plugin.py on results/vv_detection, one V-V review of the merged candidates and
              scoring with results/vl_review -> results_with/ (the merged review, as in the full C run).
Each video holds one checked GPU slot (--gpu INDEX=UUID) for its whole pipeline. Several drivers (one per allocation)
share the task list through claims/ (atomic create); a file stop_<host> makes that host's driver start no new video
(used to move the run to another allocation). Budget gate on the standard-price
estimate of all calls. Run inside an owned Slurm allocation, under scripts/openai_api_env.sh."""
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
ROOT = EXP.parents[1]
SCRIPTS = ROOT / 'scripts'
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
PRICE = (0.10, 0.01, 0.50)
LOCK = threading.Lock()
# API provider loader (owner, 2026-11-11: switch to OpenRouter); set from --provider in main().
LOADER = ['openrouter_env.sh']
sys.path.insert(0, str(SCRIPTS))
import episode_contract as contract_io  # noqa: E402


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')


def log(**row):
    with LOCK, open(EXP / 'events.jsonl', 'a') as h:
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
               EECBENCH_API_MODEL='gpt-6-luna', **(env_extra or {}))
    start = time.time()
    (base / 'logs').mkdir(parents=True, exist_ok=True)
    with open(base / 'logs' / f'{name}.log', 'w') as h:
        rc = subprocess.call([str(SCRIPTS / LOADER[0]), *map(str, cmd)], stdout=h, stderr=subprocess.STDOUT,
                             cwd=str(ROOT), env=env)
    log(event=name, task=base.name, exit_code=rc, seconds=round(time.time() - start, 1))
    return rc


def done(base, name):
    return (base / 'stages' / f'{name}.done').is_file()


def mark(base, name):
    write(base / 'stages' / f'{name}.done', dict(time=time.strftime('%Y-%m-%dT%H:%M:%S')))


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
            raise RuntimeError(f'{task}: interrupted pipeline; remove {base} to rerun')
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
    cpu = dict(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
    for name, cmd in [
            ('plugin', [VACE, SCRIPTS / 'run_vl_vv_unspecified_plugin.py', '--case', case, '--detection',
                        out / 'vv_detection/result.json', '--output', out_w / 'vv_plugin']),
            ('with_vv_review', [VACE, SCRIPTS / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection',
                                out_w / 'vv_plugin/result.json', '--output', out_w / 'vv_review', '--chain', 'v6']),
            ('with_episode_scoring', [VACE, SCRIPTS / 'run_vl_vv_branch_scoring.py', '--vl-review', out / 'vl_review/result.json',
                                      '--vv-review', out_w / 'vv_review/result.json', '--output', out_w / 'episode_scoring',
                                      '--chain', 'v6'])]:
        if done(base, name):
            continue
        target = {'plugin': out_w / 'vv_plugin', 'with_vv_review': out_w / 'vv_review',
                  'with_episode_scoring': out_w / 'episode_scoring'}[name]
        if target.exists():  # an interrupted stage starts again
            shutil.rmtree(target)
        if run(base, name, cmd, cpu):
            return f'failed at {name}'
        mark(base, name)
    return 'success'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu', action='append', default=[], metavar='INDEX=UUID')
    p.add_argument('--only', nargs='*')
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--cap', type=float, default=8.0)
    p.add_argument('--provider', choices=('openrouter', 'openai'), default='openrouter')
    a = p.parse_args()
    LOADER[0] = 'openrouter_env.sh' if a.provider == 'openrouter' else 'openai_api_env.sh'
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside an owned Slurm allocation')
    gpus = queue.Queue()
    for g in a.gpu:
        gpus.put(tuple(g.split('=', 1)))
    if gpus.empty():
        raise SystemExit('--gpu INDEX=UUID required')
    src = sources()
    tasks = (V3 / 'sample_task_ids.txt').read_text().split()
    tasks = [t for t in tasks if not a.only or t in a.only]
    log(event='driver_started', provider=a.provider, tasks=len(tasks), gpus=a.gpu, host=os.uname().nodename, slurm=os.environ['SLURM_JOB_ID'], cap=a.cap)
    reserved = {}

    (EXP / 'claims').mkdir(exist_ok=True)
    host = os.uname().nodename

    def job(t):
        if (EXP / f'stop_{host}').exists():
            return t, 'not started: stop requested'
        claim = EXP / 'claims' / t
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f'{host} {os.getpid()}'.encode())
            os.close(fd)
        except FileExistsError:
            if (EXP / 'runs' / t / 'stages' / 'with_episode_scoring.done').is_file():
                return t, 'done'
            if claim.read_text().split()[0] != host:
                return t, 'claimed elsewhere'
        with LOCK:
            if spent(EXP / 'runs') + sum(reserved.values()) + 0.2 > a.cap:
                return t, 'not started: budget gate'
            reserved[t] = 0.2
        try:
            log(event='start', task=t)
            try:
                r = video(t, src[t], gpus)
            except Exception as exc:  # noqa: BLE001 - record and continue
                r = f'failed: {type(exc).__name__}: {exc}'[:400]
            log(event='result', task=t, result=r)
            return t, r
        finally:
            with LOCK:
                reserved.pop(t, None)
    with ThreadPoolExecutor(a.threads) as pool:
        for t, r in pool.map(job, tasks):
            print(t, r, flush=True)
    log(event='driver_finished', spent_usd=round(spent(EXP / 'runs'), 4))


if __name__ == '__main__':
    main()
