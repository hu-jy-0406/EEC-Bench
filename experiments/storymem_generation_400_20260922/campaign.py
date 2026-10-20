"""Eight-node StoryMem campaign: whole-episode memory chains and strict stages."""
import argparse
import contextlib
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
FEAS = HERE.parent / 'generation_feasibility_20260921'
INPUT = HERE.parent / 'storymem_prompt_adaptation_20260922'
PY = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, path)


@contextlib.contextmanager
def locked():
    with (HERE / 'queue.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def prepare():
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    assert not (HERE / 'manifest.json').exists()
    audit = read(INPUT / 'independent_validation.json')
    assert audit['status'] == 'pass' and audit['episodes'] == 400
    source = INPUT / 'deliverables/generation_queue_400.jsonl'
    entries = [json.loads(line) for line in source.read_text().splitlines()]
    assert len(entries) == 400 and sum(e['shot_count'] for e in entries) == 2000
    snapshot = HERE / 'source_snapshot/StoryMem'
    repo = FEAS / 'repos/StoryMem'
    for path in repo.rglob('*.py'):
        if '.git' in path.parts or '__pycache__' in path.parts:
            continue
        dest = snapshot / path.relative_to(repo)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    guard = HERE.parent / 'study2_detection_only_fresh_20260918/guard_gpu.py'
    shutil.copy2(guard, HERE / 'source_snapshot/guard_gpu.py')
    shutil.copy2(FEAS / 'prompts/storymem_hps.yaml', HERE / 'source_snapshot/storymem_hps.yaml')
    tasks = []
    for rank, entry in enumerate(entries, 1):
        assert entry['generation_priority'] == rank
        original = INPUT / 'deliverables' / entry['story_script_path']
        assert sha(original) == entry['story_script_sha256']
        target = HERE / 'inputs' / (entry['episode_id'] + '.json')
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(original, target)
        tasks.append(dict(episode_id=entry['episode_id'], rank=rank,
            stage=1 if rank <= 100 else 2 if rank <= 200 else 3,
            script=str(target), script_sha256=sha(target), mapping=entry['shots'],
            seed=int.from_bytes(hashlib.sha256(('storymem400-v1:' + entry['episode_id']).encode()).digest()[:4], 'big'),
            status='pending', attempts=0, failures=0))
    shutil.copy2(source, HERE / 'input_queue_400.jsonl')
    assert [sum(len(t['mapping']) for t in tasks if t['stage'] == k) for k in (1, 2, 3)] == [500, 500, 1000]
    files = [p for p in (HERE / 'source_snapshot').rglob('*') if p.is_file()]
    files += list(HERE.glob('*.py')) + list(HERE.glob('*.sbatch'))
    manifest = dict(created=time.time(), source=str(source), source_sha256=sha(source),
        code_hashes={str(p.relative_to(HERE)): sha(p) for p in files},
        episodes=400, shots=2000, nodes=8, gpu_workers=64,
        model='StoryMem Wan2.2-MI2V-A14B; independent T2V first shot',
        size=[832, 480], frames_per_shot=81, fps=16, steps=40, solver='unipc',
        guidance=3.5, t2v_shift=12, m2v_shift=4, memory_cap=10, fixed_initial_memory=3,
        lora_rank=128, precision='official BF16 conversion and CPU offload, no quantization',
        negative_prompt='unchanged official settings',
        prompt_policy='frozen audited native StoryMem input, no rewriting or extension',
        stage_policy='all100 complete before next100; all200 complete before final200',
        memory_policy='unchanged official HPS/CLIP selection and bank; sequential shots per episode',
        seed_policy='SHA256(storymem400-v1:<episode_id>) first32bits; native per-shot seed offsets',
        max_failed_attempts_per_episode=2, api_calls=0, api_tokens=0, api_usd=0)
    write(HERE / 'manifest.json', manifest)
    with locked():
        assert not (HERE / 'queue.json').exists()
        write(HERE / 'queue.json', dict(created=time.time(), stage=1, tasks=tasks))
    print(json.dumps(status()))


def begin_job():
    manifest = read(HERE / 'manifest.json')
    for name, expected in manifest['code_hashes'].items():
        assert sha(HERE / name) == expected, f'Frozen source changed: {name}'
    assert int(os.environ['SLURM_JOB_NUM_NODES']) == 8
    assert read(HERE / 'preflight.json')['status'] == 'pass'
    job = os.environ['SLURM_JOB_ID']
    restart = int(os.environ.get('SLURM_RESTART_COUNT', '0'))
    run = f'{job}.{restart}'
    with locked():
        q = read(HERE / 'queue.json')
        old = q.get('active_job')
        if any(t['status'] == 'running' for t in q['tasks']):
            assert old, 'Running tasks have no recorded owner job.'
            if old['job'] == job:
                assert restart > old['restart'], 'Cannot duplicate a live batch.'
            else:
                state = subprocess.check_output(['squeue', '-h', '-j', old['job'], '-o', '%T'], text=True).strip()
                assert not state, f'Previous job still exists: {state}'
            for task in q['tasks']:
                if task['status'] == 'running':
                    attempt = HERE / 'attempts' / task['episode_id'] / f"attempt_{task['attempts']:03d}"
                    result_path = attempt / 'validation.json'
                    if result_path.is_file():
                        result = read(result_path)
                        assert result['status'] == 'pass' and result['script_sha256'] == task['script_sha256']
                        for artifact in result['shots'] + [result['concatenated']]:
                            assert sha(artifact['path']) == artifact['sha256']
                        dest = HERE / 'videos' / task['episode_id']
                        dest.parent.mkdir(exist_ok=True)
                        if not dest.exists():
                            dest.symlink_to((attempt / 'native').resolve(), target_is_directory=True)
                        assert dest.resolve() == (attempt / 'native').resolve()
                        task.update(status='done', result=result, recovered_validated_output=True, ended=time.time())
                    else:
                        task.update(status='pending', interrupted_run=task.get('run'), interrupted=time.time())
        q['active_job'] = dict(job=job, restart=restart, run=run, started=time.time())
        write(HERE / 'queue.json', q)
    print('JOB_READY', run, flush=True)


def claim(worker, run):
    with locked():
        q = read(HERE / 'queue.json')
        assert q['active_job']['run'] == run
        for stage in (1, 2, 3):
            group = [t for t in q['tasks'] if t['stage'] == stage]
            if all(t['status'] == 'done' for t in group):
                continue
            q['stage'] = stage
            pending = next((t for t in group if t['status'] == 'pending'), None)
            if pending is None:
                return 'wait' if any(t['status'] == 'running' for t in group) else 'failed'
            pending.update(status='running', worker=worker, run=run, started=time.time(), attempts=pending['attempts'] + 1)
            write(HERE / 'queue.json', q)
            return dict(pending)
        return None


def finish(task, worker, run, result=None, error=None):
    with locked():
        q = read(HERE / 'queue.json')
        current = next(t for t in q['tasks'] if t['episode_id'] == task['episode_id'])
        assert (current['status'], current['worker'], current['run'], current['attempts']) == (
            'running', worker, run, task['attempts'])
        if error:
            current['failures'] += 1
            current.update(status='pending' if current['failures'] < 2 else 'failed', error=error, ended=time.time())
        else:
            current.update(status='done', result=result, ended=time.time())
        write(HERE / 'queue.json', q)


def status():
    from collections import Counter
    q = read(HERE / 'queue.json')
    return dict(timestamp=time.time(), active_job=q.get('active_job'),
        stages={str(k): dict(Counter(t['status'] for t in q['tasks'] if t['stage'] == k)) for k in (1, 2, 3)},
        complete_episodes=sum(t['status'] == 'done' for t in q['tasks']),
        complete_shots=sum(len(t['mapping']) for t in q['tasks'] if t['status'] == 'done'))


def inference_env(worker):
    env = os.environ.copy()
    for key in ['USE_TORCH', 'USE_TF', 'USE_FLAX', 'CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES', 'MASTER_ADDR', 'MASTER_PORT']:
        env.pop(key, None)
    env.update(PYTHONPATH=f'{FEAS}/storymem_deps:{FEAS}/deps:{HERE}/source_snapshot/StoryMem',
        PYTHONNOUSERSITE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_XET='1',
        TOKENIZERS_PARALLELISM='false', RANK='0', LOCAL_RANK='0', WORLD_SIZE='1',
        OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4',
        STORYMEM_CLIP_CHECKPOINT=str(FEAS / 'models/CLIP/ViT-B-32-openai.pt'),
        STORYMEM_CLIP_ROOT=str(FEAS / 'models/CLIP'),
        STORYMEM_HPS_CONFIG=str(HERE / 'source_snapshot/storymem_hps.yaml'),
        STORYMEM_HPS_CHECKPOINT=str(FEAS / 'models/HPSv3/HPSv3.safetensors'))
    cache = Path('/tmp') / 'eec_storymem400' / os.environ.get('SLURM_JOB_ID', 'preflight') / worker
    for key, name in [('MIOPEN_USER_DB_PATH', 'miopen'), ('MIOPEN_CUSTOM_CACHE_DIR', 'miopen'),
                      ('TORCHINDUCTOR_CACHE_DIR', 'inductor'), ('TRITON_CACHE_DIR', 'triton')]:
        path = cache / name
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    return env


def command(task, native, log, first, gpu, uuid):
    cmd = [PY, str(HERE / 'source_snapshot/guard_gpu.py'), str(gpu), uuid,
        PY, '-u', str(HERE / 'source_snapshot/StoryMem/pipeline.py'),
        '--story_script_path', task['script'], '--t2v_model_path', str(FEAS / 'models/Wan2.2-T2V-A14B'),
        '--i2v_model_path', str(FEAS / 'models/Wan2.2-I2V-A14B'),
        '--lora_weight_path', str(FEAS / 'models/StoryMem/Wan2.2-MI2V-A14B'),
        '--size', '832*480', '--max_memory_size', '10', '--fix', '3', '--output_dir', str(native),
        '--log_file', str(log), '--offload_model', '--convert_model_dtype', '--lora_rank', '128',
        '--mi2v', '--sample_solver', 'unipc', '--sample_steps', '40', '--frame_num', '81',
        '--sample_guide_scale', '3.5', '--seed', str(task['seed'])]
    if first:
        cmd.append('--t2v_first_shot')
    return cmd


def worker(args):
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    run = f"{os.environ['SLURM_JOB_ID']}.{os.environ.get('SLURM_RESTART_COUNT', '0')}"
    state = dict(worker=args.worker, node=socket.gethostname(), pid=os.getpid(), run=run,
                 gpu=args.gpu, uuid=args.uuid, cpus=sorted(os.sched_getaffinity(0)), state='starting')
    stop = threading.Event()
    def heartbeat():
        while not stop.is_set():
            write(HERE / 'workers' / f'{args.worker}.json', dict(state, heartbeat=time.time()))
            stop.wait(30)
    threading.Thread(target=heartbeat, daemon=True).start()
    env = inference_env(args.worker)
    consecutive_errors = 0
    try:
        while not (HERE / 'STOP').exists():
            task = claim(args.worker, run)
            if task is None:
                state['state'] = 'complete'
                return
            if task == 'failed':
                raise RuntimeError('Current stage has exhausted failures; later stages remain blocked.')
            if task == 'wait':
                state['state'] = 'waiting_for_stage'
                time.sleep(20)
                continue
            attempt = HERE / 'attempts' / task['episode_id'] / f"attempt_{task['attempts']:03d}"
            native = attempt / 'native'
            native.mkdir(parents=True, exist_ok=False)
            state.update(state='generating', episode_id=task['episode_id'], attempt=str(attempt), started=time.time())
            try:
                assert sha(task['script']) == task['script_sha256']
                write(attempt / 'input.json', task)
                times = {}
                for first, phase in [(True, 't2v'), (False, 'memory')]:
                    state.update(phase=phase)
                    cmd = command(task, native, attempt / f'{phase}.model.log', first, args.gpu, args.uuid)
                    write(attempt / f'{phase}.command.json', cmd)
                    started = time.monotonic()
                    with (attempt / f'{phase}.terminal.log').open('w') as output:
                        proc = subprocess.Popen(cmd, cwd=HERE / 'source_snapshot/StoryMem', env=env,
                            stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                        state['child_pid'] = proc.pid
                        try:
                            rc = proc.wait(timeout=12 * 3600)
                        except BaseException:
                            os.killpg(proc.pid, signal.SIGTERM)
                            try:
                                proc.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                os.killpg(proc.pid, signal.SIGKILL)
                                proc.wait()
                            raise
                    times[phase] = dict(seconds=time.monotonic() - started, returncode=rc)
                    write(attempt / 'timings.json', times)
                    assert rc == 0, f'{phase} failed with exit {rc}; see {attempt}'
                    state.pop('child_pid', None)
                state['state'] = 'validating'
                result_path = attempt / 'validation.json'
                subprocess.run([PY, str(HERE / 'validate_episode.py'), str(attempt), str(result_path)],
                               env=env, check=True)
                result = read(result_path)
                dest = HERE / 'videos' / task['episode_id']
                dest.parent.mkdir(exist_ok=True)
                assert not dest.exists(), 'Refuse to overwrite a published episode.'
                dest.symlink_to(native.resolve(), target_is_directory=True)
                finish(task, args.worker, run, result=result)
                consecutive_errors = 0
                print('EPISODE_DONE', task['episode_id'], flush=True)
            except BaseException:
                error = traceback.format_exc()
                write(attempt / 'failure.json', dict(error=error, time=time.time()))
                finish(task, args.worker, run, error=error)
                consecutive_errors += 1
                print('EPISODE_FAILED', task['episode_id'], error, flush=True)
                if consecutive_errors >= 2:
                    raise RuntimeError('Two consecutive worker failures; stopping this worker.')
        state['state'] = 'stopped_between_episodes'
    except BaseException:
        state.update(state='failed', error=traceback.format_exc())
        raise
    finally:
        stop.set()
        write(HERE / 'workers' / f'{args.worker}.json', dict(state, heartbeat=time.time()))


def finalize():
    result = status()
    write(HERE / 'last_status.json', result)
    if result['complete_episodes'] != 400:
        raise SystemExit('Not all400 episodes complete; retained queue and attempts for recovery.')
    write(HERE / 'complete.json', dict(result, status='complete', completed=time.time()))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'begin-job', 'status', 'worker', 'finalize'])
    p.add_argument('--worker')
    p.add_argument('--gpu', type=int)
    p.add_argument('--uuid')
    a = p.parse_args()
    if a.action == 'prepare': prepare()
    elif a.action == 'begin-job': begin_job()
    elif a.action == 'status': print(json.dumps(status(), indent=2))
    elif a.action == 'finalize': finalize()
    else: worker(a)
