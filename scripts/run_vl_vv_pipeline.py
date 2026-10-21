#!/usr/bin/env python3
"""Run one prepared VL/VV case through the current pipeline.

This orchestrates existing stage entrypoints. It never prepares model-specific
videos or requests Slurm resources. Use --dry-run to inspect a case without
starting GPU work or API calls.

Default chain (discovery v5 -> review v6 -> scoring v5, 2026-10-09): V-L and V-V
are separate branches with separate model calls.  After the detection registry,
the V-L branch (vl_detection -> vl_review) and the V-V branch (vv_detection ->
vv_review) run concurrently as two independent chains; episode_scoring waits
for both and scores V-L, V-V within/cross and the unintentional-entity subset
separately.  Older single-list chains (discovery v1-v4) stay selectable.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import episode_shot_segments as shot_segments  # noqa: E402
API = SCRIPTS / 'openai_api_env.sh'
DETECTION = SCRIPTS / 'run_vl_vv_detection.py'
# Model transport shared by every stage; hashed so a run records the image
# labelling code it used (shot/frame labels before each image, default on).
TRANSPORT = (SCRIPTS / 'eec_api_codex_shim.py', SCRIPTS / 'gs_prompt_binding.py',
             SCRIPTS / 'run_wedetect_shot_entities.py')
DISCOVERY = SCRIPTS / 'run_vl_vv_issue_discovery.py'
REVIEW = SCRIPTS / 'run_vl_vv_issue_review.py'
SCORING = SCRIPTS / 'run_vl_vv_episode_scoring.py'
DISCOVERY_PROMPT = ROOT / 'prompts/vl_vv_issue_discovery_v1.txt'
REVIEW_PROMPT = ROOT / 'prompts/vl_vv_issue_review_v1.txt'
SCORING_SKILL = ROOT / 'skills/vl-vv-episode-scorer/SKILL.md'
BRANCH_DETECTION = SCRIPTS / 'run_vl_vv_branch_detection.py'
BRANCH_REVIEW = SCRIPTS / 'run_vl_vv_branch_review.py'
BRANCH_SCORING = SCRIPTS / 'run_vl_vv_branch_scoring.py'
# Discovery protocol v5 (branch-separated V-L / V-V, review v6, scoring v5) is
# the default since 2026-10-09.  The single-issue-list chains stay available:
# v4 = checklist, one label per issue (a discrepancy that is both V-V and V-L
# becomes two linked issues), with contract/global entity descriptions applied
# in every shot where the entity appears; v3 (without that rule) and v2
# (non-exclusive labels on one issue).  After v2-v4 the default review is v5
# (confirmed / rejected / uncertain on the core problem of each label, with the
# same entity-description rule); --review-protocol v4 or v2 keeps earlier
# reviews.  All are scored with scoring v3.  Discovery v1 keeps the historical
# review v1 / scoring v2 chain.
STAGE_FILES = {
    'v1': dict(discovery_prompt=DISCOVERY_PROMPT, review_prompt=REVIEW_PROMPT, scoring_prompt=SCORING_SKILL,
               scoring_protocol='vl_vv_episode_scoring_v2'),
    'v2': dict(discovery_prompt=ROOT / 'prompts/vl_vv_issue_discovery_v2.txt',
               review_prompt=ROOT / 'prompts/vl_vv_issue_review_v2.txt',
               scoring_prompt=ROOT / 'prompts/vl_vv_episode_scoring_v3.txt',
               scoring_protocol='vl_vv_episode_scoring_v3'),
}
STAGE_FILES['v3'] = dict(STAGE_FILES['v2'], discovery_prompt=ROOT / 'prompts/vl_vv_issue_discovery_v3.txt')
STAGE_FILES['v4'] = dict(STAGE_FILES['v2'], discovery_prompt=ROOT / 'prompts/vl_vv_issue_discovery_v4.txt')
# Discovery v5 = the branch-separated chain: separate V-L and V-V detection
# calls, separate review v6 calls, scoring v5 (separate V-L / V-V severity
# calls).  Its prompt, schema and config files are listed in BRANCH_FILES.
BRANCH_PROTOCOL = 'v5'
BRANCH_FILES = dict(
    discovery_prompt=[ROOT / 'prompts/vl_vv_issue_discovery_v5_vl.txt', ROOT / 'prompts/vl_vv_issue_discovery_v5_vv.txt'],
    review_prompt=[ROOT / 'prompts/vl_vv_issue_review_v6_vl.txt', ROOT / 'prompts/vl_vv_issue_review_v6_vv.txt'],
    scoring_prompt=[ROOT / 'prompts/vl_vv_episode_scoring_v5_vl.txt', ROOT / 'prompts/vl_vv_episode_scoring_v5_vv.txt'],
    shared=[ROOT / 'prompts/vl_vv_branch_definitions_v1.txt', ROOT / 'prompts/vl_vv_validation_repair_v2.txt',
            ROOT / 'configs/vl-vv-branch-v1.json', ROOT / 'schemas/vl-vv-branch-records-v1.schema.json',
            SCRIPTS / 'vl_vv_branch_common.py'],
    scoring_protocol='vl_vv_episode_scoring_v5')
DEFAULT_DISCOVERY_PROTOCOL = BRANCH_PROTOCOL
DISCOVERY_PROTOCOLS = ('v1', 'v2', 'v3', 'v4', BRANCH_PROTOCOL)
# Review protocols for each discovery protocol (first = default) and the files
# each review protocol uses downstream.
REVIEW_PROTOCOLS = {'v1': ('v1',), 'v2': ('v5', 'v4', 'v2'), 'v3': ('v5', 'v4', 'v2'), 'v4': ('v5', 'v4', 'v2'),
                    BRANCH_PROTOCOL: ('v6',)}
REVIEW_FILES = {
    'v1': dict(review_prompt=REVIEW_PROMPT, scoring_prompt=SCORING_SKILL, scoring_protocol='vl_vv_episode_scoring_v2'),
    'v2': {key: STAGE_FILES['v2'][key] for key in ('review_prompt', 'scoring_prompt', 'scoring_protocol')},
    'v4': dict(review_prompt=ROOT / 'prompts/vl_vv_issue_review_v4.txt',
               scoring_prompt=STAGE_FILES['v2']['scoring_prompt'],
               scoring_protocol='vl_vv_episode_scoring_v3'),
    'v5': dict(review_prompt=ROOT / 'prompts/vl_vv_issue_review_v5.txt',
               scoring_prompt=STAGE_FILES['v2']['scoring_prompt'],
               scoring_protocol='vl_vv_episode_scoring_v3'),
    'v6': {key: BRANCH_FILES[key] for key in ('review_prompt', 'scoring_prompt', 'scoring_protocol')},
}


def resolve_review_protocol(discovery_protocol, review_protocol=None):
    allowed = REVIEW_PROTOCOLS[discovery_protocol]
    if review_protocol is None:
        return allowed[0]
    if review_protocol not in allowed:
        raise ValueError(f'Review protocol {review_protocol} does not apply to discovery protocol '
                         f'{discovery_protocol} (allowed: {list(allowed)})')
    return review_protocol


def chain_files(discovery_protocol, review_protocol):
    """Prompt files and expected scoring protocol of one evaluator chain."""
    if discovery_protocol == BRANCH_PROTOCOL:
        return dict(BRANCH_FILES)
    return dict(discovery_prompt=STAGE_FILES[discovery_protocol]['discovery_prompt'], **REVIEW_FILES[review_protocol])


def chain_source_files(discovery_protocol, review_protocol):
    """Every prompt/config file of a chain whose hash must stay fixed during a run."""
    files = chain_files(discovery_protocol, review_protocol)
    paths = []
    for key in ('discovery_prompt', 'review_prompt', 'scoring_prompt', 'shared'):
        value = files.get(key, [])
        paths.extend(value if isinstance(value, list) else [value])
    if discovery_protocol == BRANCH_PROTOCOL:
        paths += [BRANCH_DETECTION, BRANCH_REVIEW, BRANCH_SCORING, SCRIPTS / 'vl_vv_repair_loop.py']
    else:
        paths += [DISCOVERY, REVIEW, SCORING]
    return paths


FRONTEND_STAGES = ('detect', 'match', 'dino_prepare', 'dino', 'attach_dino')
REGISTRY_STAGES = ('issue_discovery', 'issue_review', 'episode_scoring')
BRANCH_STAGES = ('vl_detection', 'vv_detection', 'vl_review', 'vv_review', 'episode_scoring')
FULL_STAGES = FRONTEND_STAGES + REGISTRY_STAGES
# Branch of each branch-chain stage; stages of one branch run in order, the two
# branches concurrently, and episode_scoring after both.
STAGE_BRANCH = {'vl_detection': 'vl', 'vl_review': 'vl', 'vv_detection': 'vv', 'vv_review': 'vv'}


def registry_stages(discovery_protocol):
    return BRANCH_STAGES if discovery_protocol == BRANCH_PROTOCOL else REGISTRY_STAGES


def full_stages(discovery_protocol):
    return FRONTEND_STAGES + registry_stages(discovery_protocol)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_case(case, output, mode, gpu, gpu_uuid, allow_legacy_keyframes=False):
    case, output = Path(case).resolve(), Path(output).resolve()
    if not case.is_dir():
        raise ValueError(f'Prepared case is missing: {case}')
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Use a fresh output directory: {output}')
    if output == case or case in output.parents:
        raise ValueError('Place pipeline output outside the frozen case directory')
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'run.json']
    if any(not path.is_file() for path in required):
        raise ValueError('Case needs contract.json, raw_manifest.json and run.json')
    state = read(case / 'run.json')
    if state.get('protocol') != 'vl_vv_detection_v1':
        raise ValueError('Case is not a VL/VV detection case')
    manifest = read(case / 'raw_manifest.json')
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    shots = manifest.get('shots')
    if not isinstance(shots, list) or not shots:
        raise ValueError('Case manifest needs nonempty shots')
    shot_ids = set()
    for shot in shots:
        sid, frames = shot.get('shot_id'), shot.get('frames')
        if not isinstance(sid, str) or not sid or sid in shot_ids:
            raise ValueError('Manifest shot IDs must be unique nonempty strings')
        shot_ids.add(sid)
        if not isinstance(frames, list) or len(frames) != 6:
            raise ValueError(f'{sid}: exactly six keyframes are required')
        ids = [frame.get('frame_id') for frame in frames]
        if any(type(fid) is not int or fid < 0 for fid in ids) or len(set(ids)) != 6:
            raise ValueError(f'{sid}: frame IDs must be six unique nonnegative integers')
        if any(not Path(frame.get('path', '')).is_file() for frame in frames):
            raise ValueError(f'{sid}: at least one original keyframe is unavailable')
    if mode == 'from-registry':
        ledger_path = case / 'episode_entities.json'
        if state.get('status') != 'complete' or not ledger_path.is_file():
            raise ValueError('from-registry needs a completed detection case and episode_entities.json')
        ledger = read(ledger_path)
        if ledger.get('protocol') != 'vl_vv_detection_v1' or ledger.get('status') != 'matched':
            raise ValueError('Frozen entity registry is not a successful VL/VV match')
    else:
        if state.get('status') != 'prepared' or (case / 'entities').exists():
            raise ValueError('full mode needs a fresh prepared case with no detection output')
        if gpu is None or not isinstance(gpu_uuid, str) or not re.fullmatch(r'GPU-[0-9a-fA-F]+', gpu_uuid):
            raise ValueError('full mode requires physical --gpu and --gpu-uuid')
    return case, output, len(shots), sum(len(shot['frames']) for shot in shots)


def build_plan(case, output, mode, gpu=None, gpu_uuid=None, shot_workers=3,
               python=sys.executable, gpu_python=sys.executable,
               discovery_protocol=DEFAULT_DISCOVERY_PROTOCOL, allow_legacy_keyframes=False,
               review_protocol=None):
    case, output, shots, frames = validate_case(case, output, mode, gpu, gpu_uuid, allow_legacy_keyframes)
    legacy = ['--allow-legacy-nominal-keyframes'] if allow_legacy_keyframes else []
    if discovery_protocol not in DISCOVERY_PROTOCOLS:
        raise ValueError(f'Unknown discovery protocol {discovery_protocol!r}')
    review_protocol = resolve_review_protocol(discovery_protocol, review_protocol)
    if shot_workers < 1:
        raise ValueError('--shot-workers must be positive')
    py = str(Path(python).resolve())
    gpu_py = str(Path(gpu_python).resolve())
    api = [str(API), py]
    detection = [py, str(DETECTION)]
    gpu_detection = [gpu_py, str(DETECTION)]
    stages = []
    if mode == 'full':
        stages.extend([
            ('detect', api + [str(DETECTION), 'detect', '--case', str(case),
                              '--gpu', str(gpu), '--gpu-uuid', gpu_uuid,
                              '--shot-workers', str(shot_workers), '--device', 'cuda']),
            ('match', api + [str(DETECTION), 'match', '--case', str(case)]),
            ('dino_prepare', detection + ['dino_prepare', '--case', str(case)]),
            ('dino', gpu_detection + ['dino', '--case', str(case), '--gpu', str(gpu),
                                       '--gpu-uuid', gpu_uuid]),
            ('attach_dino', detection + ['attach_dino', '--case', str(case)]),
        ])
    scoring_out = output / 'episode_scoring'
    if discovery_protocol == BRANCH_PROTOCOL:
        for branch in ('vl', 'vv'):
            stages.append((f'{branch}_detection', api + [
                str(BRANCH_DETECTION), '--branch', branch, '--case', str(case),
                '--output', str(output / f'{branch}_detection')] + legacy))
        for branch in ('vl', 'vv'):
            stages.append((f'{branch}_review', api + [
                str(BRANCH_REVIEW), '--branch', branch, '--case', str(case),
                '--detection', str(output / f'{branch}_detection/result.json'),
                '--output', str(output / f'{branch}_review')] + legacy))
        stages.append(('episode_scoring', api + [
            str(BRANCH_SCORING), '--vl-review', str(output / 'vl_review/result.json'),
            '--vv-review', str(output / 'vv_review/result.json'), '--output', str(scoring_out)]))
    else:
        discovery_out = output / 'issue_discovery'
        review_out = output / 'issue_review'
        stages.extend([
            ('issue_discovery', api + [str(DISCOVERY), '--case', str(case),
                                       '--output', str(discovery_out), '--protocol', discovery_protocol] + legacy),
            ('issue_review', api + [str(REVIEW), '--case', str(case), '--issues',
                                    str(discovery_out / 'result.json'), '--output', str(review_out),
                                    '--review-protocol', review_protocol] + legacy),
            ('episode_scoring', api + [str(SCORING), '--review',
                                       str(review_out / 'result.json'), '--output', str(scoring_out)]),
        ])
    expected = full_stages(discovery_protocol) if mode == 'full' else registry_stages(discovery_protocol)
    if tuple(name for name, _ in stages) != expected:
        raise AssertionError('Pipeline stage order changed unexpectedly')
    files = chain_files(discovery_protocol, review_protocol)

    def shown(value):
        return [str(path) for path in value] if isinstance(value, list) else str(value)

    return dict(protocol='vl_vv_pipeline_v1', mode=mode, case=str(case), output=str(output),
                python=py, gpu_python=gpu_py,
                shot_count=shots, keyframe_count=frames, model='gpt-6-luna', reasoning='low',
                discovery_protocol=discovery_protocol, review_protocol=review_protocol,
                allow_legacy_nominal_keyframes=allow_legacy_keyframes,
                discovery_prompt=shown(files['discovery_prompt']), review_prompt=shown(files['review_prompt']),
                scoring_skill=shown(files['scoring_prompt']), scoring_protocol=files['scoring_protocol'],
                stages=[dict(name=name, command=command, branch=STAGE_BRANCH.get(name))
                        if discovery_protocol == BRANCH_PROTOCOL else dict(name=name, command=command)
                        for name, command in stages])


def verify_stage(name, case, output, scoring_protocol='vl_vv_episode_scoring_v2'):
    if name == 'detect':
        checks = ((case / 'run.json', 'status', 'detected'),
                  (case / 'entities/run.json', 'status', 'success'),
                  (case / 'shot_prompt_recovery/results.json', 'status', 'success'))
    elif name == 'match':
        checks = ((case / 'run.json', 'status', 'matched'),
                  (case / 'episode_entities.json', 'status', 'matched'))
    elif name == 'dino_prepare':
        if not (case / 'dino/canonical/manifest.json').is_file():
            raise ValueError('DINO preparation produced no manifest')
        return
    elif name == 'dino':
        # The downstream attach stage validates that every required DINO result exists.
        return
    elif name == 'attach_dino':
        checks = ((case / 'run.json', 'status', 'complete'),)
    elif name == 'issue_discovery':
        checks = ((output / 'issue_discovery/result.json', 'status', 'success'),)
    elif name == 'issue_review':
        path = output / 'issue_review/result.json'
        if not path.is_file() or read(path).get('review_run', {}).get('status') != 'success':
            raise ValueError('Issue review did not produce a successful result')
        return
    elif name in ('vl_detection', 'vv_detection', 'vl_review', 'vv_review'):
        path = output / name / 'result.json'
        if not path.is_file() or read(path).get('status') != 'success':
            raise ValueError(f'{name} did not produce a successful result: {path}')
        return
    elif name == 'episode_scoring':
        path = output / 'episode_scoring/result.json'
        if not path.is_file():
            raise ValueError('Episode scoring produced no result')
        result = read(path)
        if result.get('status') != 'success' or result.get('protocol') != scoring_protocol:
            raise ValueError(f'Episode scoring did not produce a successful {scoring_protocol} result')
        return
    else:
        raise ValueError(f'Unknown stage: {name}')
    for path, field, value in checks:
        if not path.is_file() or read(path).get(field) != value:
            raise ValueError(f'{name} did not produce expected {field}={value}: {path}')


def execute(plan):
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run the pipeline inside an existing Slurm allocation; --dry-run is safe on a login node')
    if plan['mode'] == 'full' and os.environ.get('EECBENCH_ALLOW_SHARED_GPU') == '1':
        raise RuntimeError('Full VL/VV pipeline requires an idle GPU; shared-GPU mode is not allowed')
    case, output = Path(plan['case']), Path(plan['output'])
    discovery_protocol = plan.get('discovery_protocol', 'v1')
    # Plans written before review v3 existed ran the per-discovery review.
    review_protocol = plan.get('review_protocol', discovery_protocol)
    files = chain_files(discovery_protocol, review_protocol)
    source_paths = [case / 'contract.json', case / 'raw_manifest.json',
                    *chain_source_files(discovery_protocol, review_protocol),
                    DETECTION, *TRANSPORT, Path(__file__).resolve()]
    if plan['mode'] == 'from-registry':
        source_paths.append(case / 'episode_entities.json')
    source_hashes = {str(path): sha(path) for path in source_paths}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'logs').mkdir()
    labels = os.environ.get('EECBENCH_IMAGE_LABELS', 'on').strip().lower()
    if labels not in ('on', 'off'):
        raise ValueError('EECBENCH_IMAGE_LABELS must be on or off')
    state = dict(plan, status='running', started=time.time(),
                 image_labels='shot_frame_v1' if labels == 'on' else 'off',
                 source_hashes=source_hashes, stage_results=[])
    write(output / 'run.json', state)
    lock = threading.Lock()

    def run_stage(stage):
        name, command = stage['name'], stage['command']
        log = output / 'logs' / f'{name}.log'
        start = time.time()
        print(f'{name}: starting', flush=True)
        with log.open('w') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        row = dict(name=name, seconds=time.time() - start, exit_code=result.returncode, log=str(log),
                   started=start)
        with lock:
            state['stage_results'].append(row)
            write(output / 'run.json', state)
        if result.returncode:
            raise RuntimeError(f'{name} exited {result.returncode}; see {log}')
        verify_stage(name, case, output, files['scoring_protocol'])
        for path, digest in source_hashes.items():
            if sha(path) != digest:
                raise ValueError(f'Immutable pipeline input changed during {name}: {path}')
        print(f'{name}: success', flush=True)
        with lock:
            write(output / 'run.json', state)

    def run_branches(block):
        """Run each branch's stages in order, the branches concurrently; wait for all."""
        chains = {}
        for stage in block:
            chains.setdefault(stage['branch'], []).append(stage)
        failures = {}

        def chain(branch, stages):
            try:
                for stage in stages:
                    run_stage(stage)
            except BaseException as exc:  # recorded and re-raised after both branches stop
                failures[branch] = exc

        threads = [threading.Thread(target=chain, args=item, name=f'branch-{item[0]}') for item in chains.items()]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if failures:
            branch, exc = sorted(failures.items())[0]
            if len(failures) > 1:
                raise RuntimeError('; '.join(f'{b}: {e}' for b, e in sorted(failures.items()))) from exc
            raise exc

    try:
        stages = plan['stages']
        index = 0
        while index < len(stages):
            if stages[index].get('branch'):
                end = index
                while end < len(stages) and stages[end].get('branch'):
                    end += 1
                run_branches(stages[index:end])
                index = end
            else:
                run_stage(stages[index])
                index += 1
        state['status'] = 'success'
        state['result_json'] = str(output / 'episode_scoring/result.json')
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = str(exc)
        raise
    finally:
        state['seconds'] = time.time() - state['started']
        write(output / 'run.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True, help='Prepared or completed detection case')
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory for this run')
    parser.add_argument('--mode', choices=('full', 'from-registry'), required=True)
    parser.add_argument('--gpu', type=int, help='Physical rocm-smi index for full mode')
    parser.add_argument('--gpu-uuid', help='Checked physical GPU UUID for full mode')
    parser.add_argument('--gpu-python', default=sys.executable,
                        help='Python runtime for the DINO GPU stage; other stages use this process Python')
    parser.add_argument('--shot-workers', type=int, default=3)
    parser.add_argument('--discovery-protocol', choices=DISCOVERY_PROTOCOLS, default=DEFAULT_DISCOVERY_PROTOCOL,
                        help='v5 (default): separate V-L and V-V branches (contract-checking template / V-V checklist '
                             'detection, separate reviews, separate scores incl. the unintentional-entity subset); '
                             'v4: one issue list, v3 + episode-wide entity descriptions; v3: checklist, one label per '
                             'issue (linked V-V / V-L pairs); v2: checklist with non-exclusive labels on one issue; '
                             'v1: historical')
    parser.add_argument('--review-protocol', choices=('v1', 'v2', 'v4', 'v5', 'v6'), default=None,
                        help='Default: v6 for discovery v5 (separate V-L / V-V reviews); v5 for discovery v2-v4 '
                             '(core-problem verdicts, episode-wide entity descriptions), v1 for discovery v1; v4 = '
                             'core-problem verdicts without the entity rule; v2 = previous per-label review. v2, v4 and '
                             'v5 are scored with scoring v3, v6 with scoring v5')
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--dry-run', action='store_true', help='Validate inputs and print commands only')
    args = parser.parse_args()
    plan = build_plan(args.case, args.output, args.mode, args.gpu, args.gpu_uuid,
                      args.shot_workers, gpu_python=args.gpu_python,
                      discovery_protocol=args.discovery_protocol,
                      allow_legacy_keyframes=args.allow_legacy_nominal_keyframes,
                      review_protocol=args.review_protocol)
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        execute(plan)


if __name__ == '__main__':
    main()
