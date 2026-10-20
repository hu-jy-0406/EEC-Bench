#!/usr/bin/env python3
"""Auto-wait for allocated GPU node, then automatically launch/resume evaluation from Episode 4."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02')
PROJ = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench')
MONITOR_JOBS = ['230237', '229942', '229943']


def get_running_job():
    try:
        cmd = ['squeue', '-h', '-u', 'guangyi.chen', '-t', 'RUNNING', '-o', '%i|%N|%j|%b']
        output = subprocess.check_output(cmd, text=True)
        for line in output.splitlines():
            if not line.strip(): continue
            parts = line.strip().split('|')
            if len(parts) >= 3:
                job_id, node, name = parts[0], parts[1], parts[2]
                if job_id in MONITOR_JOBS or name.startswith('eec-'):
                    return job_id, node
    except Exception:
        pass
    return None, None


def get_gpu_map(job_id):
    out = subprocess.check_output(['srun', f'--jobid={job_id}', 'rocm-smi', '--showuniqueid'], text=True)
    matches = re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)', out)
    gpu_map = []
    for idx, uid in matches[:5]:
        gpu_map.append(f"{idx}=GPU-{uid.lower()}")
    return gpu_map


def is_controller_running():
    res = subprocess.run(['pgrep', '-f', 'run_batch.py'], capture_output=True)
    return res.returncode == 0


def main():
    print(f"[{time.strftime('%X')}] Auto-runner started. Watching jobs {MONITOR_JOBS}...", flush=True)
    while True:
        if is_controller_running():
            print(f"[{time.strftime('%X')}] Batch controller is actively running.", flush=True)
            time.sleep(30)
            continue

        job_id, node = get_running_job()
        if not job_id:
            time.sleep(15)
            continue

        print(f"[{time.strftime('%X')}] Found running allocation: Job {job_id} on node {node}!", flush=True)
        try:
            gpu_map = get_gpu_map(job_id)
            if len(gpu_map) < 5:
                print(f"Error: expected at least 5 GPUs, got {gpu_map}", flush=True)
                time.sleep(15)
                continue

            print(f"[{time.strftime('%X')}] Resolved GPU map: {gpu_map}", flush=True)
            launcher_sh = ROOT / 'start_run02.sh'
            gpu_args = " \\\n  ".join(f"--gpu {g}" for g in gpu_map)
            script_content = f"""#!/usr/bin/env bash
set -euo pipefail

EXP_ROOT="{ROOT}"
PROJECT_ROOT="{PROJ}"

exec srun --jobid={job_id} \\
  "${{PROJECT_ROOT}}/EECBench/scripts/openai_api_env.sh" \\
  /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python \\
  "${{PROJECT_ROOT}}/EECBench/experiments/vl_vv_multimodel_first200_20260926/run_batch.py" \\
  --batch "${{PROJECT_ROOT}}/EECBench/experiments/vl_vv_multimodel_first200_20260926/batch" \\
  --exp-dir "${{EXP_ROOT}}" \\
  {gpu_args} \\
  --max-workers 5 \\
  --shot-workers 2 \\
  > "${{EXP_ROOT}}/controller.log" 2>&1
"""
            launcher_sh.write_text(script_content)
            launcher_sh.chmod(0o755)

            print(f"[{time.strftime('%X')}] Launching controller inside Job {job_id}...", flush=True)
            subprocess.Popen([f"nohup {launcher_sh} > {ROOT/'launcher.log'} 2>&1 &"], shell=True)
            print(f"[{time.strftime('%X')}] Controller launched successfully! Now monitoring...", flush=True)
            time.sleep(60)
        except Exception as e:
            print(f"Error during launch: {e}", flush=True)
            time.sleep(15)


if __name__ == '__main__':
    main()
