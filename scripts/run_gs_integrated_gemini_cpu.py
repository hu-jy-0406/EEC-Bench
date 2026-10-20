#!/usr/bin/env python3
"""Bounded CPU-only complete Gemini pipeline on an existing owned allocation."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import run_gs_integrated_gemini as gemini
from run_isolated_shot_static_3d import owned_compute_job

p = gemini.pipeline
ADAPTERS = p.B / 'experiments/study3/cpu_adapters'


def cpu_plan(case, stop_after='spatial'):
    jobs = gemini.plan(case, 0, 'unused-cpu', stop_after, 'safe_spatial_medium')
    for job in jobs:
        command = job['command']
        if Path(command[1]).name == 'guard_gpu.py':
            command = command[4:]
        stage = job['stage']
        if stage == 'detection_and_clustering':
            index = command.index('--gpu')
            command[index:index + 2] = ['--device', 'cpu']
            command += ['--detector-timeout', '7200']
        elif stage == 'geocalib':
            command = [str(p.GEOM), str(ADAPTERS / 'calibrate_cpu.py'), str(case)]
        elif stage.startswith('pi3x_'):
            command[1] = str(ADAPTERS / 'geometry_cpu.py')
        elif stage.startswith('boxer_'):
            command[1] = str(ADAPTERS / 'boxer_cpu.py')
        elif stage == 'roma_matches':
            command[1] = str(ADAPTERS / 'roma_cpu.py')
        job['command'] = list(map(str, command))
    return jobs


def bind_cores(job, cores):
    details = subprocess.check_output(['scontrol', 'show', 'job', str(job), '-d', '-o'], text=True)
    cpu_ids = re.search(r'CPU_IDs=([0-9,-]+)', details)
    if not cpu_ids:
        raise RuntimeError('Cannot establish allocated CPU IDs')
    allocated = set()
    for part in cpu_ids[1].split(','):
        ends = list(map(int, part.split('-')))
        allocated.update(range(ends[0], ends[-1] + 1))
    if len(cores) != 4 or not set(cores) <= allocated & os.sched_getaffinity(0):
        raise ValueError('Choose exactly four allocated CPUs')
    def counters():
        return {int(words[0][3:]): list(map(int, words[1:9]))
            for line in Path('/proc/stat').read_text().splitlines()
            if (words := line.split())[0][3:].isdigit() and words[0].startswith('cpu')}
    before = counters()
    time.sleep(1)
    after = counters()
    busy = {c: 1 - ((after[c][3] + after[c][4]) - (before[c][3] + before[c][4])) /
        max(1, sum(after[c]) - sum(before[c])) for c in cores}
    if any(value >= .15 for value in busy.values()):
        raise RuntimeError('Selected CPU core is busy: ' + str(busy))
    os.sched_setaffinity(0, cores)
    return busy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['manifest', 'narrative', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--cores', required=True, help='Four idle allocated CPU IDs, comma separated')
    parser.add_argument('--stop-after', choices=['identity', 'presence', 'spatial'], default='spatial')
    args = parser.parse_args()
    job = owned_compute_job()
    case = args.output.resolve()
    cores = list(map(int, args.cores.split(',')))
    busy = bind_cores(job, cores)
    env = os.environ.copy()
    env.update(ROCR_VISIBLE_DEVICES='-1', HIP_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='',
        OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1',
        XFORMERS_DISABLED='1', TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1',
        TOKENIZERS_PARALLELISM='false', CASE_ROOT=str(case),
        PYTHONPATH=str(p.B / 'experiments/shot_scene_boxes_goal_20260916/deps'))
    subprocess.run([str(p.GEOM), '-c',
        'import torch; assert not torch.cuda.is_available() and torch.cuda.device_count()==0'], env=env, check=True)
    gemini.prepare(case, args.manifest.resolve(), args.narrative.resolve(),
        p.FRONT / 'study2/yyfz233--Pi3X_download.json',
        p.B / 'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar')
    runtime = p.runtime_profile('safe_spatial_medium')
    runtime.update(execution_device='cpu', cpu_threads=4, cpu_cores=cores,
        precision='FP32 local models; not numerically equivalent to GPU mixed precision',
        overlap_roma_with_identity=False)
    p.save(case / 'runtime_profile.json', runtime)
    p.save(case / 'cpu_preflight.json', dict(job=job, cores=cores, sampled_busy=busy,
        rss_limit_gib=24, gpu_visible_count=0))
    for key, name in [('MPLCONFIGDIR', 'matplotlib'), ('XDG_CACHE_HOME', 'cache'), ('YOLO_CONFIG_DIR', 'yolo')]:
        folder = case / 'runtime_cache' / name
        folder.mkdir(parents=True)
        env[key] = str(folder)
    jobs = cpu_plan(case, args.stop_after)
    p.save(case / 'plan.json', jobs)
    provenance = p.read(case / 'provenance.json')
    sources = [*map(Path, provenance['source_hashes']), Path(__file__), *ADAPTERS.glob('*')]
    for source in sources:
        if not source.is_file():
            continue
        dest = case / 'code_snapshot' / source.relative_to(p.B)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        provenance['source_hashes'][str(source)] = p.sha(source)
    p.save(case / 'provenance.json', provenance)

    def monitored_run(command, **kwargs):
        import psutil
        process = subprocess.Popen(command, start_new_session=True, **kwargs)
        root = psutil.Process(process.pid)
        peak = 0
        while process.poll() is None:
            try:
                children = root.children(recursive=True)
                rss = sum(child.memory_info().rss for child in [root, *children] if child.is_running())
                peak = max(peak, rss)
                p.save(case / 'cpu_monitor.json', dict(pid=process.pid, rss_bytes=rss,
                    peak_rss_bytes=peak, command=command))
                if rss > 24 * 1024**3:
                    for child in reversed(children):
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    process.terminate()
                    process.wait(timeout=20)
                    raise RuntimeError('CPU stage exceeded 24 GiB RSS limit')
            except psutil.NoSuchProcess:
                pass
            time.sleep(2)
        return subprocess.CompletedProcess(command, process.returncode)

    p.execute(case, jobs, env, job, run=monitored_run, overlap_roma=False)


if __name__ == '__main__':
    main()
