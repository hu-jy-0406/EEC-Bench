#!/usr/bin/env python3
"""WeDetect all keyframes, then bounded parallel isolated Codex shot clustering."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'EECBench/skills/wedetect-shot-entities'
DETECTOR = ROOT / 'EECBench/experiments/study_inconsistent_2/detector_upgrade_20260910'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def load_manifest(path):
    data = read(path)
    shots = data['shots']
    if not shots:
        raise ValueError('No shots')
    seen = set()
    for shot in shots:
        sid = shot['shot_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid) or sid in seen:
            raise ValueError('Shot IDs must be unique safe directory names')
        seen.add(sid)
        frames = shot['frames']
        if not frames:
            raise ValueError('No keyframes: ' + sid)
        ids = set()
        last_time = -math.inf
        for frame in frames:
            fid = frame['frame_id']
            if type(fid) is not int or fid < 0 or fid in ids:
                raise ValueError('Frame IDs must be unique nonnegative integers')
            ids.add(fid)
            stamp = frame['timestamp_sec']
            if type(stamp) not in (float, int) or not math.isfinite(stamp) or stamp < last_time:
                raise ValueError('Keyframes must have chronological finite timestamps')
            last_time = stamp
            image = (path.parent / frame['path']).resolve()
            frame.update(path=str(image), sha256=sha(image))
    return shots


def safe_compute():
    listing = subprocess.check_output(['squeue', '-h', '-u', 'guangyi.chen', '-t', 'RUNNING', '-o', '%i|%N'], text=True)
    host = socket.gethostname().split('.')[0]
    for line in listing.splitlines():
        job, nodes = line.strip().split('|', 1)
        hosts = subprocess.check_output(['scontrol', 'show', 'hostnames', nodes], text=True).splitlines()
        if host in hosts:
            return job
    raise RuntimeError('Run on a compute node in an existing guangyi.chen allocation')


def check_gpu(gpu, out):
    job = safe_compute()
    status = subprocess.check_output(['rocm-smi', '--showuse', '--showmeminfo', 'vram', '--showpidgpus'], text=True)
    (out / 'gpu_check.txt').write_text(status)
    use = re.search(rf'GPU\[{gpu}\].*GPU use \(%\):\s*(\d+)', status)
    mem = re.search(rf'GPU\[{gpu}\].*VRAM Total Used Memory \(B\):\s*(\d+)', status)
    mappings = re.findall(r'PID (\d+) is using (\d+) DRM device\(s\)(?::\s*\n([^\n]*))?', status)
    if 'GPUs Indexed by PID' not in status or re.search(r'error|permission denied', status, re.I):
        raise RuntimeError('Cannot establish KFD process mappings')
    for pid, count, devices in mappings:
        if int(count) and (len(devices.split()) != int(count) or str(gpu) in devices.split()):
            raise RuntimeError(f'GPU occupied or KFD mapping incomplete: PID {pid}')
    if not use or not mem or int(use[1]) != 0 or int(mem[1]) > 100 * 1024**2:
        raise RuntimeError('GPU is not genuinely idle')
    return job


def run_process(command, prompt, cwd, stdout, stderr, timeout):
    with stdout.open('w') as log, stderr.open('w') as err:
        proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=log,
                                stderr=err, text=True, start_new_session=True)
        try:
            proc.communicate(prompt, timeout=timeout)
        except BaseException:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise
        if proc.returncode:
            raise RuntimeError(f'Process failed ({proc.returncode}); see {stderr}')


def detect(shots, args, out):
    inputs = out / 'detector_inputs'
    for shot in shots:
        bundle = inputs / shot['shot_id'] / 'input_bundle'
        bundle.mkdir(parents=True)
        refs = []
        for frame in shot['frames']:
            target = bundle / f"frame_{frame['frame_id']:06d}{Path(frame['path']).suffix}"
            shutil.copy2(frame['path'], target)
            refs.append(dict(frame, path=target.name))
        dump(bundle / 'shot_manifest.json', dict(shot_id=shot['shot_id'], reference_frames=refs))
    command = ['bash', str(DETECTOR / 'run_local_detector.sh'), str(args.gpu),
               str(DETECTOR / 'venv/bin/python'), '--model', 'wedetect',
               '--input-root', str(inputs), '--output', str(out / 'detections'),
               '--weights', str(DETECTOR / 'weights/wedetect_base_uni.pth'), '--seed', str(args.seed)]
    dump(out / 'detector_request.json', dict(command=command, seed=args.seed,
         adapter_sha256=sha(DETECTOR / 'wedetect_adapter.py'),
         runner_sha256=sha(DETECTOR / 'detect_keyframes_local.py')))
    # This gate is immediately before launch, never inferred from an old snapshot.
    job = check_gpu(args.gpu, out)
    dump(out / 'allocation.json', dict(job=job, host=socket.gethostname(), gpu=args.gpu))
    run_process(command, '', ROOT, out / 'detector.stdout.log', out / 'detector.stderr.log', args.detector_timeout)
    return out / 'detections'


def load_detections(directory, shots):
    run = read(directory / 'run.json')
    if run.get('status') != 'success' or run.get('model') != 'wedetect':
        raise ValueError('A successful WeDetect run is required')
    expected = {(s['shot_id'], f['frame_id']): f for s in shots for f in s['frames']}
    results = {(r['shot'], r['frame_id']): r for r in run['results']}
    if len(results) != len(run['results']) or set(results) != set(expected):
        raise ValueError('Detection coverage must exactly match all requested frames')
    output = {}
    for key, source in expected.items():
        path = directory / key[0] / f'frame_{key[1]:06d}' / 'detections.json'
        data = read(path)
        if data['shot'] != key[0] or data['frame_id'] != key[1] or data['sha256'] != source['sha256']:
            raise ValueError('Detection/image identity mismatch')
        if len(data['detections']) != results[key]['count']:
            raise ValueError('Detection count disagrees with completed run')
        w, h = data['image_size']
        seen = set()
        for d in data['detections']:
            if type(d['id']) is not int or d['id'] in seen:
                raise ValueError('Duplicate or invalid detection ID')
            seen.add(d['id'])
            validate_box(d['box_xyxy'], w, h)
        output[key] = data
    return output


def validate_box(box, width, height):
    if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
        raise ValueError('Invalid box')
    x1, y1, x2, y2 = box
    if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
        raise ValueError('Box outside original image or degenerate')


def make_payload(shot, detections):
    frames = []
    for frame in shot['frames']:
        data = detections[(shot['shot_id'], frame['frame_id'])]
        candidates = [dict(candidate_id=f"f{frame['frame_id']}:d{d['id']}",
                           name=d['label'], box_xyxy=d['box_xyxy'], score=d['score'])
                      for d in data['detections']]
        frames.append(dict(frame_id=frame['frame_id'], timestamp_sec=frame['timestamp_sec'],
                           image_size=data['image_size'], image_sha256=frame['sha256'],
                           attachment_index=len(frames) + 1, detections=candidates))
    return dict(shot_id=shot['shot_id'], frames=frames)


def validate_result(result, payload):
    import jsonschema
    jsonschema.validate(result, read(ASSETS / 'output.schema.json'))
    if result['shot_id'] != payload['shot_id']:
        raise ValueError('Wrong shot ID')
    frames = {f['frame_id']: f for f in payload['frames']}
    candidates = {d['candidate_id']: f['frame_id'] for f in payload['frames'] for d in f['detections']}
    owned = set()
    entity_ids = set()
    def claim(cid):
        if cid not in candidates or cid in owned:
            raise ValueError('Unknown or multiply-owned candidate: ' + cid)
        owned.add(cid)
    for entity in result['entities']:
        if not entity['name'].strip() or not entity['entity_id'].strip() or entity['entity_id'] in entity_ids:
            raise ValueError('Empty name/ID or duplicate entity ID')
        entity_ids.add(entity['entity_id'])
        if not entity['candidate_ids']:
            raise ValueError('Entities cannot be added without detector candidates')
        for cid in entity['candidate_ids']:
            claim(cid)
        observations = entity['observations']
        if [r['frame_id'] for r in observations] != list(frames):
            raise ValueError('Every entity must cover all frames in input order')
        for row in observations:
            if not row['reason'].strip():
                raise ValueError('Missing observation rationale')
            if row['visible']:
                if not row['exist']:
                    raise ValueError('visible requires exist')
                validate_box(row['box_xyxy'], *frames[row['frame_id']]['image_size'])
            elif row['box_xyxy'] is not None:
                raise ValueError('Invisible entities must have null boxes')
        # A claimed candidate is a retained observation, not an unrelated anchor.
        visible = {r['frame_id'] for r in observations if r['visible']}
        if any(candidates[cid] not in visible for cid in entity['candidate_ids']):
            raise ValueError('Assigned detection in a frame judged invisible; reject false detections instead')
    for rejected in result['rejected_detections']:
        claim(rejected['candidate_id'])
        if not rejected['reason'].strip():
            raise ValueError('Missing rejection reason')
    if owned != set(candidates):
        raise ValueError('Unaccounted detector candidates')
    # Derive summaries rather than trusting redundant model output.
    for entity in result['entities']:
        for flag in ('exist', 'visible'):
            ids = [r['frame_id'] for r in entity['observations'] if r[flag]]
            entity[flag + '_frame_ids'] = ids
        entity['boxes_by_frame'] = [
            dict(frame_id=r['frame_id'],
                 box_xyxy=list(r['box_xyxy']) if r['visible'] else None)
            for r in entity['observations']
        ]
    return result


def audit_events(path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    usage = []
    completed = False
    for event in events:
        if event.get('type') in ('error', 'turn.failed'):
            raise ValueError('Codex reported a failed turn')
        item = event.get('item', {})
        if item and item.get('type') not in ('reasoning', 'agent_message', 'error'):
            raise ValueError('Unexpected tool or action in isolated review: ' + str(item.get('type')))
        if event.get('type') == 'turn.completed':
            completed = True
            usage.append(event.get('usage'))
    if not completed:
        raise ValueError('No completed Codex turn')
    return usage


def disabled_skills_config():
    """Disable ambient catalogs for this call only; the chosen skill is in stdin.

    Config reference: https://learn.chatgpt.com/docs/config-file/config-reference
    Supply both directory and SKILL.md paths for CLI versions accepting either.
    No user configuration is changed and no skill contents are read.
    """
    codex_dir = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    roots = [codex_dir / 'skills', codex_dir / 'plugins/cache',
             Path.home() / '.agents/skills', Path('/etc/codex/skills')]
    paths = set()
    visited = set()
    for root in roots:
        for current, directories, files in os.walk(root, followlinks=True):
            physical = Path(current).resolve()
            if physical in visited:
                directories[:] = []
                continue
            visited.add(physical)
            if 'SKILL.md' in files:
                for folder in (Path(current), physical):
                    paths.update((str(folder), str(folder / 'SKILL.md')))
    return 'skills.config=[' + ','.join(
        '{path=' + json.dumps(path) + ',enabled=false}' for path in sorted(paths)) + ']'


def review(shot, payload, args, directory):
    directory.mkdir(parents=True)
    dump(directory / 'input.json', payload)
    skill = (ASSETS / 'SKILL.md').read_text()
    prompt = (ASSETS / 'review_prompt.txt').read_text() + '\n<skill>\n' + skill + '\n</skill>\n<shot>\n' + json.dumps(payload, ensure_ascii=False) + '\n</shot>\n'
    (directory / 'prompt.txt').write_text(prompt)
    shutil.copy2(ASSETS / 'output.schema.json', directory / 'output.schema.json')
    if args.prepare_only:
        return dict(shot_id=shot['shot_id'], status='prepared', calls=0)
    reuse_root = getattr(args, 'reuse_reviews', None)
    if reuse_root:
        previous = reuse_root.resolve() / 'shots' / shot['shot_id']
        if (previous / 'response.json').exists():
            # Reuse only a completed, tool-free response for byte-identical context.
            request = read(previous / 'request.json')
            if (read(previous / 'input.json') != payload or
                    (previous / 'prompt.txt').read_text() != prompt or
                    sha(previous / 'output.schema.json') != sha(directory / 'output.schema.json') or
                    request['model'] != args.model or request['reasoning'] != args.reasoning):
                raise ValueError('Cannot reuse a review with different inputs, prompt, schema or model')
            audit_events(previous / 'events.jsonl')
            validate_result(read(previous / 'response.json'), payload)
            for name in ('response.json', 'events.jsonl', 'stderr.log', 'request.json'):
                shutil.copy2(previous / name, directory / name)
            return finish_review(shot, payload, directory, reused_from=str(previous))
    # Outside the project tree: no ancestor project instructions or other shot files.
    with tempfile.TemporaryDirectory(prefix='eec-shot-') as tmp:
        work = Path(tmp)
        command = [args.codex_bin, '--ask-for-approval', 'never', 'exec',
                   '--ignore-user-config', '-c', disabled_skills_config(),
                   '--ephemeral', '--skip-git-repo-check',
                   '--sandbox', 'read-only', '--color', 'never', '--json',
                   '--model', args.model, '-c', f'model_reasoning_effort="{args.reasoning}"',
                   '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
                   '--output-schema', str(directory / 'output.schema.json'),
                   '--output-last-message', str(directory / 'response.json'), '--cd', str(work)]
        for feature in ('shell_tool', 'unified_exec', 'view_image', 'apps', 'plugins', 'hooks',
                        'multi_agent', 'memories', 'skill_search', 'browser_use', 'computer_use',
                        'code_mode', 'code_mode_only', 'workspace_dependencies'):
            command.extend(['--disable', feature])
        for index, frame in enumerate(shot['frames']):
            image = work / f"image_{index + 1}{Path(frame['path']).suffix}"
            shutil.copy2(frame['path'], image)
            if sha(image) != frame['sha256']:
                raise ValueError('Image changed before review')
            command.extend(['--image', str(image)])
        command.append('-')
        dump(directory / 'request.json', dict(command=command, model=args.model,
             reasoning=args.reasoning, prompt_sha256=sha(directory / 'prompt.txt'),
             schema_sha256=sha(directory / 'output.schema.json'),
             skill_sha256=sha(ASSETS / 'SKILL.md')))
        run_process(command, prompt, work, directory / 'events.jsonl', directory / 'stderr.log', args.timeout)
    return finish_review(shot, payload, directory)


def finish_review(shot, payload, directory, reused_from=None):
    usage = audit_events(directory / 'events.jsonl')
    result = validate_result(read(directory / 'response.json'), payload)
    dump(directory / 'entities.json', result)
    record = dict(shot_id=shot['shot_id'], status='success', calls=0 if reused_from else 1,
                  usage=[] if reused_from else usage, reused_from=reused_from,
                  entity_count=len(result['entities']), output_sha256=sha(directory / 'entities.json'))
    dump(directory / 'status.json', record)
    return record


def review_shots(shots, detections, args, out, state):
    """Only the coordinator writes run state; workers receive one shot payload."""
    pending = iter(shots)
    records = {}
    failures = []
    workers = min(args.shot_workers, len(shots))
    state.update(shot_workers=workers, active_shots=[], review_started=time.time())

    def task(shot, payload):
        started = time.time()
        directory = out / 'shots' / shot['shot_id']
        try:
            record = review(shot, payload, args, directory)
        except Exception as exc:
            record = dict(shot_id=shot['shot_id'], status='failed', error=str(exc))
        record.update(started=started, finished=time.time())
        dump(directory / 'status.json', record)
        return record

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        active = {}
        def fill():
            while not failures and len(active) < workers:
                shot = next(pending, None)
                if shot is None:
                    break
                future = pool.submit(task, shot, make_payload(shot, detections))
                active[future] = shot['shot_id']
        fill()
        while active:
            state['active_shots'] = list(active.values())
            dump(out / 'run.json', state)
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                sid = active.pop(future)
                record = future.result()
                records[sid] = record
                if record['status'] == 'failed':
                    failures.append(sid)
            state['shots'] = [records[s['shot_id']] for s in shots if s['shot_id'] in records]
            # Stop scheduling on failure; already running isolated calls finish.
            fill()
    state.update(active_shots=[], review_finished=time.time())
    dump(out / 'run.json', state)
    if failures:
        raise RuntimeError('Shot reviews failed: ' + ', '.join(failures))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--gpu', type=int)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--shot-workers', type=int, default=3, help='Maximum independent concurrent shot reviews; 1 runs serially')
    p.add_argument('--spatial-relations', action='store_true', help='After all entity reviews succeed, run independent spatial-relation subagents')
    p.add_argument('--detections', type=Path)
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--reuse-reviews', type=Path, help='Explicitly reuse completed reviews with identical context; missing shots get fresh calls')
    p.add_argument('--model', default='gpt-6-astra')
    p.add_argument('--reasoning', choices=['low', 'medium', 'high', 'xhigh', 'max', 'ultra'], default='medium')
    p.add_argument('--codex-bin', default='codex')
    p.add_argument('--timeout', type=int, default=1200)
    p.add_argument('--detector-timeout', type=int, default=1800)
    args = p.parse_args()
    if not args.detections and (args.gpu is None or args.gpu < 0):
        p.error('--gpu PHYSICAL_INDEX is required for fresh inference')
    if args.shot_workers < 1:
        p.error('--shot-workers must be positive')
    shots = load_manifest(args.manifest.resolve())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(status='running', shots=[], detector_mode='reuse' if args.detections else 'fresh',
                 started=time.time(), script_sha256=sha(__file__))
    dump(out / 'manifest.json', dict(shots=shots))
    dump(out / 'run.json', state)
    try:
        if not args.prepare_only:
            safe_compute()
        directory = args.detections.resolve() if args.detections else detect(shots, args, out)
        state['detections'] = str(directory)
        state['detector_run_sha256'] = sha(directory / 'run.json')
        detections = load_detections(directory, shots)
        review_shots(shots, detections, args, out, state)
        if args.spatial_relations:
            if args.prepare_only:
                state['spatial_relations'] = dict(status='waiting_for_entities')
            else:
                import run_shot_spatial_relations as spatial
                state['spatial_relations'] = spatial.run(out, out / 'spatial_relations', args, allow_running=True)
        state.update(status='prepared' if args.prepare_only else 'success', finished=time.time())
        state.pop('active_shot', None)
    except BaseException as exc:
        state.update(status='failed', error=str(exc), finished=time.time())
        dump(out / 'run.json', state)
        raise
    dump(out / 'run.json', state)
    print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    main()
