#!/usr/bin/env python3
"""Read-only check of the GPUs visible in this Slurm step: use, VRAM, KFD processes and UUID per GPU,
sampled twice 30 s apart, plus API reachability.  A GPU counts as idle only if both samples show 0% use,
at most 100 MiB VRAM in use and no KFD process (the same rule as the pipeline's own check_gpu)."""
import json
import re
import socket
import subprocess
import sys
import time


def sample():
    status = subprocess.check_output(['rocm-smi', '--showuse', '--showmeminfo', 'vram', '--showpidgpus'], text=True)
    ids = subprocess.check_output(['rocm-smi', '--showuniqueid'], text=True)
    if 'GPUs Indexed by PID' not in status:
        raise RuntimeError('Cannot establish KFD process mappings')
    complete, kfd = True, set()
    for pid, count, devices in re.findall(r'PID (\d+) is using (\d+) DRM device\(s\)(?::\s*\n([^\n]*))?', status):
        names = (devices or '').split()
        kfd.update(int(d) for d in names if d.isdigit())
        complete &= not int(count) or len(names) == int(count)
    rows = {}
    for gpu in sorted({int(g) for g in re.findall(r'GPU\[(\d+)\]', status)}):
        use = re.search(rf'GPU\[{gpu}\].*GPU use \(%\):\s*(\d+)', status)
        mem = re.search(rf'GPU\[{gpu}\].*VRAM Total Used Memory \(B\):\s*(\d+)', status)
        uid = re.search(rf'GPU\[{gpu}\].*Unique ID:\s*0x([0-9a-fA-F]+)', ids)
        rows[gpu] = dict(index=gpu, use=int(use[1]) if use else None, vram_bytes=int(mem[1]) if mem else None,
                         uuid=f'GPU-{uid[1]}' if uid else None, kfd_process=gpu in kfd)
        rows[gpu]['idle'] = bool(complete and use and mem and uid and int(use[1]) == 0
                                 and int(mem[1]) <= 100 * 1024**2 and gpu not in kfd)
    return status, rows


def main():
    first_status, first = sample()
    time.sleep(30)
    second_status, second = sample()
    api = subprocess.run(['curl', '-s', '-o', '/dev/null', '-m', '15', '-w', '%{http_code}',
                          'https://api.openai.com/v1/models'], capture_output=True, text=True).stdout
    gpus = [dict(second[g], idle=first.get(g, {}).get('idle', False) and second[g]['idle']) for g in sorted(second)]
    result = dict(host=socket.gethostname(), time=time.time(), api_http=api, gpus=gpus,
                  idle=[f"{g['index']}={g['uuid']}" for g in gpus if g['idle']])
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as stream:
            json.dump(dict(result, rocm_smi=[first_status, second_status]), stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
