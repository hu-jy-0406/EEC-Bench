"""Safely stop this node's HoloCine workers and requeue their episodes."""
import json, os, signal, socket, time
from pathlib import Path
from campaign import ROOT, read, write, locked

node = socket.gethostname()
manager_audit = []
for path in sorted((ROOT / 'managers').glob(f'*_{node}.json')):
    manager = read(path)
    pid = manager.get('pid')
    if not isinstance(pid, int):
        continue
    proc = Path('/proc') / str(pid)
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        if not (any(arg.endswith(b'node_manager.py') for arg in args) and proc.stat().st_uid == os.getuid()):
            manager_audit.append({'pid': pid, 'not_a_live_campaign_manager': True})
            continue
        os.kill(pid, signal.SIGSTOP)
        manager_audit.append({'pid': pid, 'suspended_before_worker_stop': True})
    except (FileNotFoundError, ProcessLookupError):
        manager_audit.append({'pid': pid, 'already_exited': True})
rows = []
for path in sorted((ROOT / 'workers').glob('*.json')):
    worker = read(path)
    if worker.get('node') != node:
        continue
    pid = int(worker['pid'])
    proc = Path('/proc') / str(pid)
    audit = {'worker': worker['worker'], 'pid': pid, 'state_before': worker.get('state')}
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        assert str(ROOT / 'campaign.py').encode() in args and worker['worker'].encode() in args
        assert proc.stat().st_uid == os.getuid()
        os.kill(pid, signal.SIGTERM)
        audit['sigterm_sent'] = True
    except (FileNotFoundError, ProcessLookupError):
        audit['already_exited'] = True
    rows.append((path, worker, audit))

deadline = time.time() + 90
while time.time() < deadline and any((Path('/proc') / str(w['pid'])).exists() for _, w, _ in rows):
    time.sleep(1)
alive = [w['worker'] for _, w, _ in rows if (Path('/proc') / str(w['pid'])).exists()]
if alive:
    raise RuntimeError(f'workers did not exit after SIGTERM: {alive}')

now = time.time()
names = {w['worker'] for _, w, _ in rows}
for path, worker, audit in rows:
    worker.update(state='stopped_user_directed_node_release', process_exit_verified=True, stopped_at=now)
    write(path, worker)
    audit['process_exit_verified'] = True
for manager in manager_audit:
    if manager.get('suspended_before_worker_stop'):
        try:
            os.kill(manager['pid'], signal.SIGTERM)
            manager['terminated_after_worker_stop'] = True
        except ProcessLookupError:
            manager['already_exited'] = True
with locked():
    queue = read(ROOT / 'queue.json')
    for task in queue['tasks']:
        if task.get('worker') in names and task['status'] == 'running':
            task.setdefault('interruptions', []).append({
                'at': now, 'reason': 'user_requested_node_release',
                'worker': task['worker'], 'attempt': task['attempts'],
            })
            task['status'] = 'pending'
            task['max_attempts'] = max(task.get('max_attempts', 2), task['attempts'] + 1)
    write(ROOT / 'queue.json', queue)
audit_dir = ROOT / 'node_pauses'
audit_dir.mkdir(exist_ok=True)
write(audit_dir / f'{node}.json', {'node': node, 'time': now, 'reason': 'user_requested_node_release', 'managers': manager_audit, 'workers': [a for _, _, a in rows]})
print(json.dumps({'node': node, 'paused_workers': sorted(names), 'audit': str(audit_dir / f'{node}.json')}))
