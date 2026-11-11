#!/usr/bin/env python3
"""Step 2b: arms on the 20 audited videos (owner, 2026-11-10; see README "Owner decisions").

A  frozen code (code/EECBench), original WeDetect detections: fresh shot clustering, detect (binding + Grounding DINO
   prompt recovery, GPU), matching v2, V-V detection/review, V-L detection/review, episode scoring.
B  same, but clustering gets the augmented detections (aug_detections/<task>: chosen Grounding DINO boxes of the
   discovered background objects appended).
C  on B's case: V-V detection, V-V review and scoring with code_vv/EECBench (checklist + W8, X10), V-L review of B.
D  on A's case: the same with code_vv.
Model stages: GPT-6 Luna, reasoning low (stage defaults), API transport. Phase 1 (A, B): one worker per GPU given as
--gpu INDEX=UUID; phase 2 (C, D): API-only threads. Logs: arms/events.jsonl, per stage logs in each run folder.
"""
import argparse, json, os, queue, shutil, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
CODE = {'A': EXP / 'code/EECBench', 'B': EXP / 'code/EECBench', 'C': EXP / 'code_vv/EECBench', 'D': EXP / 'code_vv/EECBench',
        'C2': EXP / 'code_vv2/EECBench', 'D2': EXP / 'code_vv2/EECBench'}
DERIVED = {'entities', 'shot_prompt_recovery', 'global_match_v2', 'episode_entities.json', 'global_entities', 'dino'}
LOCK = threading.Lock()


def log(**row):
    with LOCK, open(EXP / 'arms/events.jsonl', 'a') as h:
        h.write(json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S'), **row)) + '\n')


def sources():
    states = {}
    for path in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in json.loads(path.read_text())['tasks'].items():
            if t.get('status') == 'success': states[tid] = t
    rows = json.loads((V3 / 'miss_diagnosis/audit20/index.json').read_text())
    return {r['task']: Path(states[r['task']]['case_dir']).resolve() for r in rows}


def run_stage(base, name, cmd, code, env_extra):
    env = os.environ.copy(); env.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false',
                                        EECBENCH_REVIEW_PYTHON=VACE, **env_extra)
    start = time.time()
    with open(base / f'{name}.log', 'w') as h:
        code_rc = subprocess.call([str(code / 'scripts/openai_api_env.sh'), *map(str, cmd)], stdout=h, stderr=subprocess.STDOUT,
                                  cwd=str(code), env=env)
    return code_rc, round(time.time() - start, 1)


def full_arm(task, src, arm, gpu):
    base = EXP / 'arms' / arm / task; case, out = base / 'case', base / 'results'
    if (out / 'episode_scoring/result.json').is_file(): return 'skipped'
    if base.exists(): shutil.rmtree(base)
    base.mkdir(parents=True)
    shutil.copytree(src, case, ignore=lambda d, names: [n for n in names if Path(d) == src and n in DERIVED])
    st = json.loads((case / 'run.json').read_text())
    st.update(status='prepared', arm=arm, experiment='vl_vv_background_discovery_20261110', copied_from=str(src))
    for k in ('detected_at', 'matched_at', 'matching_protocol', 'detector_device', 'binding_protocol'): st.pop(k, None)
    (case / 'run.json').write_text(json.dumps(st, indent=1)); out.mkdir()
    code = CODE[arm]; S = code / 'scripts'
    dets = src / 'entities/detections' if arm == 'A' else EXP / 'aug_detections' / task
    cpu = dict(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
    stages = [
        ('clustering', [VACE, S / 'run_wedetect_shot_entities.py', '--manifest', case / 'raw_manifest.json', '--output', case / 'entities',
                        '--device', 'cpu', '--model', 'gpt-6-luna', '--reasoning', 'low', '--shot-workers', '3', '--detections', dets], cpu),
        ('detect', [VACE, S / 'run_vl_vv_detection.py', 'detect', '--case', case, '--device', 'cuda', '--gpu', gpu[0], '--gpu-uuid', gpu[1],
                    '--shot-workers', '3'], {}),
        ('match', [VACE, S / 'run_vl_vv_detection.py', 'match', '--case', case], cpu),
        ('vv_detection', [VACE, S / 'run_vl_vv_branch_detection.py', '--branch', 'vv', '--case', case, '--output', out / 'vv_detection', '--chain', 'v6'], cpu),
        ('vv_review', [VACE, S / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection', out / 'vv_detection/result.json',
                       '--output', out / 'vv_review', '--chain', 'v6'], cpu),
        ('vl_detection', [VACE, S / 'run_vl_vv_branch_detection.py', '--branch', 'vl', '--case', case, '--output', out / 'vl_detection', '--chain', 'v6'], cpu),
        ('vl_review', [VACE, S / 'run_vl_vv_branch_review.py', '--branch', 'vl', '--case', case, '--detection', out / 'vl_detection/result.json',
                       '--output', out / 'vl_review', '--chain', 'v6'], cpu),
        ('episode_scoring', [VACE, S / 'run_vl_vv_branch_scoring.py', '--vl-review', out / 'vl_review/result.json', '--vv-review',
                             out / 'vv_review/result.json', '--output', out / 'episode_scoring', '--chain', 'v6'], cpu)]
    log(event='start', arm=arm, task=task, gpu=gpu[0])
    for name, cmd, env in stages:
        rc, sec = run_stage(base, name, cmd, code, env)
        log(event=name, arm=arm, task=task, exit_code=rc, seconds=sec)
        if rc: return f'failed at {name}'
    return 'success'


def vv_arm(task, arm):
    host = 'B' if arm in ('C', 'C2') else 'A'
    hb = EXP / 'arms' / host / task; case = hb / 'case'
    if not (hb / 'results/episode_scoring/result.json').is_file(): return f'host {host} not finished'
    base = EXP / 'arms' / arm / task; out = base / 'results'
    if (out / 'episode_scoring/result.json').is_file(): return 'skipped'
    if base.exists(): shutil.rmtree(base)
    out.mkdir(parents=True)
    code = CODE[arm]; S = code / 'scripts'; cpu = dict(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
    stages = [
        ('vv_detection', [VACE, S / 'run_vl_vv_branch_detection.py', '--branch', 'vv', '--case', case, '--output', out / 'vv_detection', '--chain', 'v6']),
        ('vv_review', [VACE, S / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection', out / 'vv_detection/result.json',
                       '--output', out / 'vv_review', '--chain', 'v6']),
        ('episode_scoring', [VACE, S / 'run_vl_vv_branch_scoring.py', '--vl-review', hb / 'results/vl_review/result.json', '--vv-review',
                             out / 'vv_review/result.json', '--output', out / 'episode_scoring', '--chain', 'v6'])]
    log(event='start', arm=arm, task=task, host=host)
    for name, cmd in stages:
        rc, sec = run_stage(base, name, cmd, code, cpu)
        log(event=name, arm=arm, task=task, exit_code=rc, seconds=sec)
        if rc: return f'failed at {name}'
    return 'success'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['full', 'vv'], required=True)
    p.add_argument('--gpu', action='append', default=[], metavar='INDEX=UUID')
    p.add_argument('--arms', default=None, help='Comma list; default A,B for full and C,D for vv')
    p.add_argument('--only', nargs='*', help='Task ids')
    p.add_argument('--threads', type=int, default=6)
    a = p.parse_args()
    if not os.environ.get('SLURM_JOB_ID'): raise RuntimeError('Run inside an owned Slurm allocation')
    (EXP / 'arms').mkdir(exist_ok=True)
    src = sources()
    tasks = [t for t in src if not a.only or t in a.only]
    if a.phase == 'full':
        arms = (a.arms or 'A,B').split(',')
        gpus = [tuple(g.split('=', 1)) for g in a.gpu]
        if not gpus: raise SystemExit('--gpu INDEX=UUID required for phase full')
        q = queue.Queue()
        for t in tasks:
            for arm in arms: q.put((t, arm))
        log(event='phase_full_started', jobs=q.qsize(), gpus=gpus, host=os.uname().nodename, slurm=os.environ['SLURM_JOB_ID'])

        def worker(gpu):
            while True:
                try: t, arm = q.get_nowait()
                except queue.Empty: return
                r = full_arm(t, src[t], arm, gpu); print(arm, t, r, flush=True); log(event='result', arm=arm, task=t, result=r)
        threads = [threading.Thread(target=worker, args=(g,)) for g in gpus]
        for th in threads: th.start()
        for th in threads: th.join()
    else:
        arms = (a.arms or 'C,D').split(',')
        jobs = [(t, arm) for t in tasks for arm in arms]
        log(event='phase_vv_started', jobs=len(jobs))
        with ThreadPoolExecutor(a.threads) as pool:
            for (t, arm), r in zip(jobs, pool.map(lambda j: vv_arm(*j), jobs)):
                print(arm, t, r, flush=True); log(event='result', arm=arm, task=t, result=r)
    log(event=f'phase_{a.phase}_finished')


if __name__ == '__main__':
    main()
