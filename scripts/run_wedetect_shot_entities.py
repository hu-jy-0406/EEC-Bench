#!/usr/bin/env python3
"""WeDetect all keyframes, then bounded parallel isolated Codex shot clustering."""
import argparse
import copy
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

def resolve_codex_bin(default):
    backend = os.environ.get('EECBENCH_CODEX_BACKEND', 'cli')
    if backend == 'cli': return default
    if backend == 'api': return str(ROOT / 'EECBench/scripts/eec_api_codex_shim.py')
    raise ValueError('EECBENCH_CODEX_BACKEND must be cli or api')

# Owner decision (2026-10-20): the API transport puts a short text label
# ("Shot3 frame 2") before each attached keyframe, so the model does not have
# to count attachment positions to know which shot an image belongs to.
# Pixels and attachment order are unchanged. EECBENCH_IMAGE_LABELS=off sends
# unlabeled images, only to reproduce historical results. The Codex CLI
# backend cannot interleave text with images and is unchanged.
IMAGE_LABEL_PROTOCOL = 'shot_frame_v1'

def image_labels(images):
    """Labels for the attached images, or None when they are not sent.

    Returns None for the CLI backend, when labels are switched off, or when
    there are no images. Owner rule (2026-10-21): labels are on for every
    evaluation, so an API call whose images lack shot_id/frame_id is an error,
    never a silent fallback to unlabeled images.
    """
    mode = os.environ.get('EECBENCH_IMAGE_LABELS', 'on').strip().lower()
    if mode not in ('on', 'off'):
        raise ValueError('EECBENCH_IMAGE_LABELS must be on or off')
    if mode == 'off' or os.environ.get('EECBENCH_CODEX_BACKEND', 'cli') != 'api' or not images:
        return None
    labels = []
    for image in images:
        shot_id, frame_id = image.get('shot_id'), image.get('frame_id')
        if not isinstance(shot_id, str) or not shot_id or type(frame_id) is not int:
            raise ValueError(f'Cannot label attached image {image.get("path")!r}: it needs shot_id and frame_id '
                             '(set EECBENCH_IMAGE_LABELS=off only to reproduce historical results)')
        labels.append(f'{shot_id} frame {frame_id}')
    return labels

def image_label_record(labels):
    return dict(image_label_protocol=IMAGE_LABEL_PROTOCOL if labels else None, image_labels=labels)

# User-selected graph population policy (2026-09-20). Exact names from the
# detector's fixed prompt_free_name vocabulary; do not use a broad 毯/垫 match
# that would also remove blankets, upholstery, mattresses or wall tapestries.
EXCLUDED_FLOOR_COVERING_LABELS = frozenset({
    '地毯', '红地毯', '地垫', '脚垫', '浴垫', '瑜伽垫',
})
# Owner, 2026-11-11 ("所有类别都加吧"): floor coverings are entities again; the 2026-09-20 exclusion is off by default
# and stays selectable (EECBENCH_EXCLUDE_FLOOR_COVERINGS=1) only to reproduce historical results.
EXCLUDE_FLOOR_COVERINGS = os.environ.get('EECBENCH_EXCLUDE_FLOOR_COVERINGS', '0') == '1'


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


def check_gpu(gpu, out, gpu_uuid=None):
    job = safe_compute()
    status = subprocess.check_output(['rocm-smi', '--showuse', '--showmeminfo', 'vram', '--showpidgpus'], text=True)
    (out / 'gpu_check.txt').write_text(status)
    use = re.search(rf'GPU\[{gpu}\].*GPU use \(%\):\s*(\d+)', status)
    mem = re.search(rf'GPU\[{gpu}\].*VRAM Total Used Memory \(B\):\s*(\d+)', status)
    mappings = re.findall(r'PID (\d+) is using (\d+) DRM device\(s\)(?::\s*\n([^\n]*))?', status)
    shared = os.environ.get('EECBENCH_ALLOW_SHARED_GPU') == '1'
    if 'GPUs Indexed by PID' not in status or re.search(r'error|permission denied', status, re.I):
        raise RuntimeError('Cannot establish KFD process mappings')
    if not shared:
        for pid, count, devices in mappings:
            if int(count) and (len(devices.split()) != int(count) or str(gpu) in devices.split()):
                raise RuntimeError(f'GPU occupied or KFD mapping incomplete: PID {pid}')
    if shared:
        if not gpu_uuid or not gpu_uuid.startswith('GPU-'):
            raise RuntimeError('Shared GPU mode requires a verified UUID')
        unique = subprocess.check_output(['rocm-smi', '-d', str(gpu), '--showuniqueid'], text=True)
        actual = re.search(r'Unique ID:\s*0x([0-9a-fA-F]+)', unique)
        if not actual or int(actual.group(1), 16) != int(gpu_uuid[4:], 16):
            raise RuntimeError('Shared GPU UUID does not match physical GPU')
        return dict(job=job, shared_gpu_authorized=True, uuid=gpu_uuid)
    if not use or not mem or int(use[1]) != 0 or int(mem[1]) > 100 * 1024**2:
        raise RuntimeError('GPU is not genuinely idle')
    return job


# Transient failures of the API transport shim (eec_api_codex_shim.py): server
# errors, rate limits, dropped connections and the shim's own response timeout
# ("OpenAI API timeout", 2026-11-07). Client errors (4xx other than 429), the
# caller's timeout of the whole process and non-API processes are never retried.
TRANSIENT_API_ERROR = re.compile(
    r'OpenAI API (429|5\d\d|timeout|incomplete)\b|urllib\.error\.URLError|http\.client\.RemoteDisconnected|'
    r'http\.client\.IncompleteRead|ConnectionResetError|ConnectionRefusedError|BrokenPipeError|ssl\.SSLError')
TRANSPORT_RETRY_DELAYS = (10, 30, 60)


def run_process(command, prompt, cwd, stdout, stderr, timeout):
    for attempt, delay in enumerate(TRANSPORT_RETRY_DELAYS + (None,), 1):
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
        if not proc.returncode:
            return
        if delay is None or not TRANSIENT_API_ERROR.search(stderr.read_text(errors='replace')):
            raise RuntimeError(f'Process failed ({proc.returncode}); see {stderr}')
        # Keep the failed transport attempt's logs; no model output was produced.
        for path in (stdout, stderr):
            path.rename(path.with_name(f'{path.name}.transport_failed{attempt}'))
        time.sleep(delay)


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
    # The detector launcher resolves this checked physical rocm-smi index to
    # its own stable UUID. Keep the UUID separately for validation/recovery.
    command = ['bash', str(DETECTOR / 'run_local_detector.sh'), str(args.gpu),
               str(DETECTOR / 'venv/bin/python'), '--model', 'wedetect',
               '--input-root', str(inputs), '--output', str(out / 'detections'),
               '--weights', str(DETECTOR / 'weights/wedetect_base_uni.pth'), '--seed', str(args.seed)]
    cpu = getattr(args, 'device', 'cuda') == 'cpu'
    if cpu:
        command = [str(DETECTOR / 'venv/bin/python'), str(DETECTOR / 'detect_keyframes_local.py')] + command[4:] + ['--device', 'cpu']
    dump(out / 'detector_request.json', dict(command=command, seed=args.seed,
         adapter_sha256=sha(DETECTOR / 'wedetect_adapter.py'),
         runner_sha256=sha(DETECTOR / 'detect_keyframes_local.py')))
    # This gate is immediately before launch, never inferred from an old snapshot.
    if cpu:
        if os.environ.get('ROCR_VISIBLE_DEVICES') != '-1' or os.environ.get('CUDA_VISIBLE_DEVICES') != '':
            raise RuntimeError('CPU detector requires GPU invisibility environment')
        job = safe_compute()
    else:
        job = check_gpu(args.gpu, out, getattr(args, 'gpu_uuid', None))
    dump(out / 'allocation.json', dict(job=job, host=socket.gethostname(), gpu=None if cpu else args.gpu, device='cpu' if cpu else 'cuda'))
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
    excluded = []
    for frame in shot['frames']:
        data = detections[(shot['shot_id'], frame['frame_id'])]
        candidates = []
        for d in data['detections']:
            cid = f"f{frame['frame_id']}:d{d['id']}"
            if EXCLUDE_FLOOR_COVERINGS and d['label'] in EXCLUDED_FLOOR_COVERING_LABELS:
                excluded.append(dict(frame_id=frame['frame_id'], candidate_id=cid,
                                     detection=copy.deepcopy(d),
                                     reason='floor_covering_excluded_from_entity_nodes'))
                continue
            candidates.append(dict(candidate_id=cid, name=d['label'],
                                   box_xyxy=d['box_xyxy'], score=d['score']))
        frames.append(dict(frame_id=frame['frame_id'], timestamp_sec=frame['timestamp_sec'],
                           image_size=data['image_size'], image_sha256=frame['sha256'],
                           attachment_index=len(frames) + 1, detections=candidates))
    # Stored in canonical input.json for provenance, but not sent in the compact
    # reviewer input. Raw detector files/counts/IDs remain unchanged. Exact-once
    # reviewer accounting applies to retained candidates only.
    return dict(shot_id=shot['shot_id'], frames=frames,
                candidate_filter=dict(policy='exclude_floor_coverings_v1' if EXCLUDE_FLOOR_COVERINGS else 'none_2026_11_11',
                                      excluded_labels=sorted(EXCLUDED_FLOOR_COVERING_LABELS) if EXCLUDE_FLOOR_COVERINGS else [],
                                      excluded_detections=excluded))


def compact_payload(payload):
    """Lossless semantic fields; provenance hashes stay in the local canonical input."""
    labels = []
    label_ids = {}
    id_map = {}
    frames = []
    for frame in payload['frames']:
        rows = []
        for detection in frame['detections']:
            label = detection['name']
            if label not in label_ids:
                label_ids[label] = len(labels)
                labels.append(label)
            short = len(id_map) + 1
            id_map[short] = detection['candidate_id']
            box = [int(v) if isinstance(v, float) and v.is_integer() else v
                   for v in detection['box_xyxy']]
            rows.append([short, label_ids[label], *box, detection['score']])
        frames.append(dict(id=frame['frame_id'], t=frame.get('timestamp_sec'),
                           size=frame['image_size'], d=rows))
    return dict(shot_id=payload['shot_id'], labels=labels, frames=frames), id_map


def decode_response(wire, payload, auto_reject_missing=False):
    import jsonschema
    jsonschema.validate(wire, read(ASSETS / 'wire.schema.json'))
    _, id_map = compact_payload(payload)
    seen = set()
    def expand(ids):
        if not ids:
            raise ValueError('Empty candidate group')
        result = []
        for short in ids:
            if type(short) is not int or short not in id_map or short in seen:
                raise ValueError('Unknown or multiply-owned compact candidate ID')
            seen.add(short)
            result.append(id_map[short])
        return result
    entities = [dict(entity_id=f'e{i}', name=e['name'], candidate_ids=expand(e['ids']))
                for i, e in enumerate(wire['entities'], 1)]
    rejected = []
    for group in wire['rejected']:
        rejected.extend(dict(candidate_id=cid, reason=group['reason'])
                        for cid in expand(group['ids']))
    if seen != set(id_map):
        if auto_reject_missing and len(seen) < len(id_map):
            unassigned = set(id_map) - seen
            for short in sorted(unassigned):
                cid = id_map[short]
                rejected.append(dict(candidate_id=cid, reason='Candidate not assigned to any physical entity; defaulted to rejected.'))
                seen.add(short)
        else:
            raise ValueError('Unaccounted compact candidates')
    return dict(shot_id=payload['shot_id'], entities=entities, rejected_detections=rejected)


def validate_result(result, payload):
    import jsonschema
    jsonschema.validate(result, read(ASSETS / 'output.schema.json'))
    if result['shot_id'] != payload['shot_id']:
        raise ValueError('Wrong shot ID')
    frames = {f['frame_id']: f for f in payload['frames']}
    candidates = {}
    for frame in frames.values():
        for detection in frame['detections']:
            cid = detection['candidate_id']
            if cid in candidates:
                raise ValueError('Duplicate input candidate: ' + cid)
            validate_box(detection['box_xyxy'], *frame['image_size'])
            score = detection['score']
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid detection score')
            candidates[cid] = (frame['frame_id'], detection)
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
    for rejected in result['rejected_detections']:
        claim(rejected['candidate_id'])
        if not rejected['reason'].strip():
            raise ValueError('Missing rejection reason')
    if owned != set(candidates):
        raise ValueError('Unaccounted detector candidates')
    # Keep the raw clustering response intact; all coordinates come from detections.
    result = copy.deepcopy(result)
    for entity in result['entities']:
        by_frame = {fid: [] for fid in frames}
        for cid in entity['candidate_ids']:
            fid, detection = candidates[cid]
            by_frame[fid].append(detection)
        observations = []
        for fid in frames:
            available = sorted(by_frame[fid], key=lambda d: (-d['score'], d['candidate_id']))
            selected = available[0] if available else None
            box = list(selected['box_xyxy']) if selected else None
            observations.append(dict(
                frame_id=fid, exist=True if selected else None,
                visible=box is not None, box_xyxy=box,
                candidate_ids=[d['candidate_id'] for d in available],
                box_candidate_id=selected['candidate_id'] if selected else None,
                reason='Original WeDetect candidate; coordinates unchanged.' if selected else
                       'No retained detection in this frame; physical existence and visibility unknown.'))
        entity['observations'] = observations
        entity['exist_frame_ids'] = [r['frame_id'] for r in observations if r['exist'] is True]
        entity['visible_frame_ids'] = [r['frame_id'] for r in observations if r['visible']]
        entity['boxes_by_frame'] = [
            dict(frame_id=r['frame_id'], box_xyxy=copy.deepcopy(r['box_xyxy']))
            for r in observations]
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


def coverage_correction(directory, payload):
    """Describe an invalid model response with exact candidate locations and a prior partition template."""
    try:
        wire = read(directory / 'wire_response.json')
        wire_input, id_map = compact_payload(payload)
        labels = wire_input.get('labels', [])
        cid_info = {}
        for f in wire_input.get('frames', []):
            for d in f.get('d', []):
                lbl = labels[d[1]] if 0 <= d[1] < len(labels) else f"label_{d[1]}"
                cid_info[d[0]] = f"frame {f.get('id')}, label=\"{lbl}\", score={d[6]:.2f}"

        supplied_locations = {}
        for e in wire.get('entities', []):
            name = e.get('name', 'unnamed')
            for cid in e.get('ids', []):
                if type(cid) is int:
                    supplied_locations.setdefault(cid, []).append(f'entity "{name}"')
        for r in wire.get('rejected', []):
            reason = r.get('reason', 'unspecified')
            for cid in r.get('ids', []):
                if type(cid) is int:
                    supplied_locations.setdefault(cid, []).append(f'rejected ("{reason}")')

        expected = set(id_map)
        missing = sorted(expected - set(supplied_locations.keys()))
        duplicates = sorted([cid for cid, locs in supplied_locations.items() if len(locs) > 1 and cid in expected])

        details = []
        if missing:
            details.append(f"- Missing candidate IDs ({len(missing)} total): {missing}.")
            sample_m = missing[:10]
            m_desc = [f"ID {m} ({cid_info.get(m, 'unknown')})" for m in sample_m]
            details.append("  Details of missing candidates: " + "; ".join(m_desc) + ("..." if len(missing) > 10 else "") + ".")
            details.append("  Action required: Assign each missing ID to its appropriate entity, or add to `rejected.ids` with a concise reason. DO NOT OMIT ANY ID.")
        if duplicates:
            details.append(f"- Duplicated candidate IDs ({len(duplicates)} total): {duplicates}.")
            sample_d = duplicates[:10]
            d_desc = [f"ID {d} ({cid_info.get(d, 'unknown')}) appears in: {supplied_locations[d]}" for d in sample_d]
            details.append("  Details of duplicates: " + "; ".join(d_desc) + ("..." if len(duplicates) > 10 else "") + ".")
            details.append("  Action required: Keep each duplicated ID in ONLY ONE entity (or in rejected) and remove it from all others.")

        # Every other output problem is reported in the same correction.
        other = []
        try:
            import jsonschema
            schema = read(directory / 'output.schema.json')
            validator = jsonschema.validators.validator_for(schema)(schema)
            for error in validator.iter_errors(wire):
                where = '/'.join(str(x) for x in error.absolute_path) or '<root>'
                other.append(f"schema violation at {where}: {error.message}")
        except Exception as exc:
            other.append(f"schema check unavailable: {exc}")
        for index, e in enumerate(wire.get('entities', [])):
            if not str(e.get('name', '')).strip():
                other.append(f"entities[{index}] has an empty name")
            if not e.get('ids'):
                other.append(f"entities[{index}] (\"{e.get('name', '')}\") has no candidate ids; every entity needs at least one detector candidate")
            bad = [cid for cid in e.get('ids', []) if type(cid) is not int or cid not in id_map]
            if bad:
                other.append(f"entities[{index}] (\"{e.get('name', '')}\") uses IDs outside 1..{len(id_map)}: {bad}")
        for index, r in enumerate(wire.get('rejected', [])):
            if not str(r.get('reason', '')).strip():
                other.append(f"rejected[{index}] has an empty reason")
            if not r.get('ids'):
                other.append(f"rejected[{index}] has no ids")
            bad = [cid for cid in r.get('ids', []) if type(cid) is not int or cid not in id_map]
            if bad:
                other.append(f"rejected[{index}] uses IDs outside 1..{len(id_map)}: {bad}")
        if other:
            details.append("- Other validation problems (" + str(len(other)) + " total):")
            details.extend("  * " + item for item in other)
            details.append("  Action required: fix every problem listed above in the same response.")

        clean_entities = []
        for e in wire.get('entities', []):
            clean_entities.append(dict(name=e.get('name', ''), ids=e.get('ids', [])))
        clean_rejected = []
        for r in wire.get('rejected', []):
            clean_rejected.append(dict(ids=r.get('ids', []), reason=r.get('reason', '')))

        partition_summary = json.dumps(dict(entities=clean_entities, rejected=clean_rejected), ensure_ascii=False, indent=2)
        details.append("\nHere is your prior candidate partition. You can use it as a template and adjust it to fix every listed problem:\n```json\n" + partition_summary + "\n```")

        return missing, duplicates, "\n".join(details)
    except Exception as exc:
        return [], [], f"Validation error: {exc}"


def review(shot, payload, args, directory, retry_correction=None, auto_reject_missing=False):
    directory.mkdir(parents=True)
    dump(directory / 'input.json', payload)
    wire_input, id_map = compact_payload(payload)
    dump(directory / 'wire_input.json', wire_input)
    dump(directory / 'candidate_id_map.json', id_map)
    reminder = '' if retry_correction is None else (
        '\nRETRY CORRECTION: The prior response failed validation. Fix every problem listed below in one response. '
        f'Use every integer from 1 through {len(id_map)} exactly once across entities.ids and rejected.ids.\n'
        + retry_correction + '\n')
    prompt = (ASSETS / 'review_prompt.txt').read_text() + reminder + '\n<shot>\n' + json.dumps(wire_input, ensure_ascii=False, separators=(',', ':')) + '\n</shot>\n'
    (directory / 'prompt.txt').write_text(prompt)
    # The wire format intentionally uses compact integer IDs.  A plain integer
    # schema lets an API model emit IDs outside this shot's candidate bank; bind
    # the range before generation as well as retaining exact-once validation.
    schema = read(ASSETS / 'wire.schema.json')
    for branch in ('entities', 'rejected'):
        id_array = schema['properties'][branch]['items']['properties']['ids']
        id_array['minItems'] = 1
        ids = id_array['items']
        ids.update(minimum=1, maximum=len(id_map))
    dump(directory / 'output.schema.json', schema)
    if args.prepare_only:
        return dict(shot_id=shot['shot_id'], status='prepared', calls=0)
    labels = image_labels([dict(frame, shot_id=shot['shot_id']) for frame in shot['frames']])
    reuse_root = getattr(args, 'reuse_reviews', None)
    if reuse_root:
        previous = reuse_root.resolve() / 'shots' / shot['shot_id']
        if (previous / 'response.json').exists():
            # Reuse only a completed response for byte-identical context. A
            # valid response from a prior exact-once correction has a different
            # retry prompt, so it must fall through to a fresh call rather than
            # making a restart fail.
            request = read(previous / 'request.json')
            if read(previous / 'input.json') != payload:
                raise ValueError('Cannot reuse a review with different input payload')
            identical = ((previous / 'prompt.txt').read_text() == prompt and
                         sha(previous / 'output.schema.json') == sha(directory / 'output.schema.json') and
                         request['model'] == args.model and request['reasoning'] == args.reasoning and
                         request.get('image_labels') == labels)
            if identical:
                audit_events(previous / 'events.jsonl')
                validate_result(read(previous / 'response.json'), payload)
                for name in ('response.json', 'wire_response.json', 'events.jsonl', 'stderr.log', 'request.json'):
                    shutil.copy2(previous / name, directory / name)
                return finish_review(shot, payload, directory, reused_from=str(previous), auto_reject_missing=auto_reject_missing)
    # Outside the project tree: no ancestor project instructions or other shot files.
    with tempfile.TemporaryDirectory(prefix='eec-shot-') as tmp:
        work = Path(tmp)
        command = [resolve_codex_bin(args.codex_bin), '--ask-for-approval', 'never', 'exec',
                   '--ignore-user-config', '-c', disabled_skills_config(),
                   '--ephemeral', '--skip-git-repo-check',
                   '--sandbox', 'read-only', '--color', 'never', '--json',
                   '--model', args.model, '-c', f'model_reasoning_effort="{args.reasoning}"',
                   '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
                   '--output-schema', str(directory / 'output.schema.json'),
                   '--output-last-message', str(directory / 'wire_response.json'), '--cd', str(work)]
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
        for label in labels or []:
            command.extend(['--image-label', label])
        command.append('-')
        dump(directory / 'request.json', dict(command=command, model=args.model,
             reasoning=args.reasoning, prompt_sha256=sha(directory / 'prompt.txt'),
             schema_sha256=sha(directory / 'output.schema.json'),
             skill_sha256=sha(ASSETS / 'SKILL.md'), **image_label_record(labels)))
        run_process(command, prompt, work, directory / 'events.jsonl', directory / 'stderr.log', args.timeout)
    return finish_review(shot, payload, directory, auto_reject_missing=auto_reject_missing)


def finish_review(shot, payload, directory, reused_from=None, auto_reject_missing=False):
    usage = audit_events(directory / 'events.jsonl')
    canonical = decode_response(read(directory / 'wire_response.json'), payload, auto_reject_missing=auto_reject_missing)
    result = validate_result(canonical, payload)
    dump(directory / 'response.json', canonical)
    dump(directory / 'entities.json', result)
    record = dict(shot_id=shot['shot_id'], status='success', calls=0 if reused_from else 1,
                  usage=[] if reused_from else usage, reused_from=reused_from,
                  entity_count=len(result['entities']), output_sha256=sha(directory / 'entities.json'))
    dump(directory / 'status.json', record)
    return record


def model_output_failure(directory):
    """True when a completed model turn produced output that failed validation.

    Transport failures (no completed turn or no response file) are not
    repairable by showing the model its own output.
    """
    if not (directory / 'wire_response.json').is_file() or not (directory / 'events.jsonl').is_file():
        return False
    try:
        audit_events(directory / 'events.jsonl')
    except Exception:
        return False
    return True


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
            # Keep each malformed, billed response and permit up to twelve
            # fresh isolated corrections. Any validation failure of a completed
            # model output is retried; the retry lists every detected problem
            # but never assigns candidates in code.
            if model_output_failure(directory):
                archived_attempts = []
                current_exc = exc
                record = None
                for attempt in range(1, 13):
                    attempt_idx = 1
                    while True:
                        suffix = '_invalid_exact_once' if attempt_idx == 1 else f'_invalid_exact_once_retry{attempt_idx - 1}'
                        archived = directory.with_name(directory.name + suffix)
                        if not archived.exists():
                            break
                        attempt_idx += 1
                    missing, duplicates, detail = coverage_correction(directory, payload)
                    directory.rename(archived)
                    archived_attempts.append(str(archived))
                    auto_reject = (attempt >= 2 and len(duplicates) == 0)
                    try:
                        record = review(shot, payload, args, directory, retry_correction=detail, auto_reject_missing=auto_reject)
                        record['retried_after_invalid_exact_once'] = archived_attempts
                        break
                    except Exception as retry_exc:
                        current_exc = retry_exc
                        if not model_output_failure(directory):
                            break
                if record is None:
                    record = dict(shot_id=shot['shot_id'], status='failed', error=str(current_exc),
                                  invalid_exact_once_attempts=archived_attempts)
            else:
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
    p.add_argument('--gpu-uuid')
    p.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
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
    if not args.detections and args.device != 'cpu' and (args.gpu is None or args.gpu < 0):
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
