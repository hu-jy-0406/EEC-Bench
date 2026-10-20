"""One Slurm task per exclusive node, eight guarded independent GPU workers."""
import csv
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import campaign


def read_cpu():
    result = {}
    for line in Path('/proc/stat').read_text().splitlines():
        parts = line.split()
        if parts[0].startswith('cpu') and parts[0] != 'cpu':
            values = list(map(int, parts[1:9]))
            result[int(parts[0][3:])] = (sum(values), values[3] + values[4])
    return result


def main():
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    assert os.environ.get('SLURM_JOB_ID')
    q = campaign.read(campaign.HERE / 'queue.json')
    run = f"{os.environ['SLURM_JOB_ID']}.{os.environ.get('SLURM_RESTART_COUNT', '0')}"
    assert q['active_job']['run'] == run
    cgroup = Path('/sys/fs/cgroup') / Path('/proc/self/cgroup').read_text().strip().split(':')[-1].lstrip('/')
    jobgroup = next(p for p in [cgroup, *cgroup.parents] if p.name == 'job_' + os.environ['SLURM_JOB_ID'])
    limit = (jobgroup / 'memory.max').read_text().strip()
    assert limit == 'max' or int(limit) >= 2 * 1024**4
    stats = dict(line.split() for line in (jobgroup / 'memory.stat').read_text().splitlines())
    if limit != 'max':
        assert int(stats['anon']) + 8 * 160 * 1024**3 < int(limit), 'Insufficient host memory for eight unmodified workers.'
    command = ['rocm-smi', '--showuniqueid', '--csv']
    cards = list(csv.DictReader(subprocess.check_output(command, text=True).splitlines()))
    cards = [c for c in cards if c.get('device', '').startswith('card')]
    assert len(cards) == 8, cards
    physical_cores = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        base = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        key = ((base / 'physical_package_id').read_text().strip(), (base / 'core_id').read_text().strip())
        physical_cores.setdefault(key, cpu)
    cores = sorted(physical_cores.values())
    assert len(cores) >= 32
    before = read_cpu()
    time.sleep(1)
    after = read_cpu()
    busy = {c: 100 * (1 - (after[c][1] - before[c][1]) / max(1, after[c][0] - before[c][0])) for c in cores}
    # Keep four real cores per worker, distributed over the allocated core set.
    groups = []
    for i in range(8):
        available = cores[i * len(cores) // 8:(i + 1) * len(cores) // 8]
        chosen = sorted(available, key=lambda c: (busy[c], c))[:4]
        assert len(chosen) == 4 and max(busy[c] for c in chosen) <= 20, (chosen, busy)
        groups.append(chosen)
    processes, records = [], []
    node = socket.gethostname()
    for i, card in enumerate(sorted(cards, key=lambda c: int(c['device'][4:]))):
        gpu = int(card['device'][4:])
        uuid = 'GPU-' + format(int(card['Unique ID'], 16), '016x')
        name = f'{run}_{node}_gpu{gpu}'
        logpath = campaign.HERE / 'logs' / f'{name}.log'
        logpath.parent.mkdir(exist_ok=True)
        log = logpath.open('a')
        command = ['taskset', '-c', ','.join(map(str, groups[i])), campaign.PY, '-u',
            str(campaign.HERE / 'campaign.py'), 'worker', '--worker', name, '--gpu', str(gpu), '--uuid', uuid]
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        processes.append((proc, log))
        records.append(dict(worker=name, pid=proc.pid, gpu=gpu, uuid=uuid, cpus=groups[i], log=str(logpath)))
        time.sleep(1)
    campaign.write(campaign.HERE / 'launches' / f'{run}_{node}.json', dict(node=node, run=run,
        workers=records, memory_limit=limit, initial_anon_bytes=int(stats['anon']), cpu_busy_percent=busy))
    print('NODE_WORKERS_STARTED', json.dumps(records), flush=True)
    exits = [proc.wait() for proc, log in processes]
    for proc, log in processes:
        log.close()
    if any(exits):
        raise SystemExit(f'Worker errors on {node}: {exits}')


if __name__ == '__main__':
    main()
