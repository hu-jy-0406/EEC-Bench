"""Requeue only proven-exited HoloCine workers from a user-reserved node."""
import argparse, os, time
from pathlib import Path
from campaign import ROOT, read, write, locked

parser = argparse.ArgumentParser()
parser.add_argument('--node', required=True)
args = parser.parse_args()
rows = []
for path in sorted((ROOT / 'workers').glob('*.json')):
    worker = read(path)
    if worker.get('node') != args.node:
        continue
    proc = Path('/proc') / str(worker['pid'])
    if proc.exists() and str(ROOT / 'campaign.py').encode() in (proc / 'cmdline').read_bytes().split(b'\0'):
        raise RuntimeError(f'live HoloCine worker remains: {worker["worker"]} pid={worker["pid"]}')
    rows.append((path, worker))

now = time.time()
names = {worker['worker'] for _, worker in rows}
for path, worker in rows:
    worker.update(state='stopped_user_directed_node_release', process_exit_verified=True, stopped_at=now)
    write(path, worker)
with locked():
    queue = read(ROOT / 'queue.json')
    for task in queue['tasks']:
        if task.get('worker') in names and task['status'] == 'running':
            task.setdefault('interruptions', []).append({'at': now, 'reason': 'user_requested_node_release', 'worker': task['worker'], 'attempt': task['attempts']})
            task['status'] = 'pending'
            task['max_attempts'] = max(task.get('max_attempts', 2), task['attempts'] + 1)
    write(ROOT / 'queue.json', queue)
audit_dir = ROOT / 'node_pauses'
audit_dir.mkdir(exist_ok=True)
write(audit_dir / f'{args.node}.json', {'node': args.node, 'time': now, 'reason': 'user_requested_node_release', 'workers': sorted(names)})
print(args.node, 'reconciled', len(names))
