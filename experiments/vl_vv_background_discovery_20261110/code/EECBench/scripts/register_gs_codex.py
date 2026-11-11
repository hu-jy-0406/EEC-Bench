#!/usr/bin/env python3
"""Direct Codex scene registration from original frames and own-shot geometry."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

from gs_consistency_contract import obj, S, N, enum
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io

B = Path(__file__).resolve().parents[1]
SCHEMA = obj(
    scale=dict(type='number', minimum=.1, maximum=10), yaw_deg=N,
    translation=dict(type='array', items=N, minItems=3, maxItems=3),
    confidence=enum('low', 'medium', 'high'), reasoning=S, limitations=S,
)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(case):
    """Preserve the validated direct experiment's evidence; never read matching."""
    case = Path(case).resolve()
    paths = [case/'narrative.json']
    paths += [case/folder/f'{sid}{suffix}.json'
              for sid in ('shot1', 'shot3')
              for folder, suffix in (('selected', '_scene'), ('inputs', ''))]
    hashes = {str(p): sha(p) for p in paths}
    shots, images = [], []
    for sid in ('shot1', 'shot3'):
        scene = read(case/'selected'/f'{sid}_scene.json')
        inp = read(case/'inputs'/f'{sid}.json')
        own = {e['entity_id']: e for e in inp['entities']}
        shots.append(dict(
            shot_id=sid, coordinate_system=scene['coordinate_system'],
            cameras=scene['cameras'],
            entities=[dict(entity_id=e['entity_id'], name=e['name'],
                           motion_status=e['motion_status'], geometry=e['geometry'],
                           observations=own[e['entity_id'].split('/')[-1]]['observations'])
                      for e in scene['entities']],
        ))
        for f in inp['frames']:
            if sha(f['path']) != f['sha256']:
                raise ValueError('Original frame hash mismatch: ' + f['path'])
            images.append(dict(f, shot_id=sid))
            hashes[str(Path(f['path']).resolve())] = f['sha256']
    payload = dict(
        stage='direct_scene_transform_estimate', normal_story_prompt=read(case/'narrative.json'),
        shots=shots,
        images=[dict(attachment_index=i+1, shot_id=f['shot_id'], frame_id=f['frame_id'])
                for i, f in enumerate(images)],
        transform_convention='Shot3 to Shot1, positive scale, right-handed Z yaw, xyz translation; model units',
    )
    return payload, images, hashes


def make_fit(response):
    """Convert the model's parameters exactly; no optimization or correction."""
    from partial_scene_contract import schema_validate
    schema_validate(response, SCHEMA)
    values = [response['scale'], response['yaw_deg'], *response['translation']]
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Non-finite direct transform')
    angle = math.radians(response['yaw_deg'])
    c, s = math.cos(angle), math.sin(angle)
    return dict(
        status='numeric_candidate', estimate_source='codex_direct',
        scale=response['scale'], yaw_deg=response['yaw_deg'],
        rotation=[[c, -s, 0.], [s, c, 0.], [0., 0., 1.]],
        translation=list(response['translation']),
        parameters=[math.log(response['scale']), angle, *response['translation']],
        confidence=response['confidence'], reasoning=response['reasoning'],
        limitations=response['limitations'],
        geometric_diagnostics=dict(status='unavailable', reason='No RoMA correspondences or numerical fit; model confidence is not measured registration accuracy'),
    )


def run(case, output=None, codex_bin='/vast/users/guangyi.chen/.local/bin/codex', timeout=1800):
    from run_isolated_shot_static_3d import owned_compute_job
    allocation = owned_compute_job()
    case = Path(case).resolve()
    output = Path(output).resolve() if output else case/'registration/roma_geometry/registration.json'
    call_dir = case/'calls/registration_direct'
    if output.exists() or call_dir.exists():
        raise FileExistsError('Refuse to overwrite direct registration or its model call; use a fresh case')
    started = time.time()
    payload, images, hashes = prepare(case)
    prompt = B/'prompts/gs_direct_registration_v1.txt'
    source_paths = [Path(__file__).resolve(), prompt, B/'scripts/run_partial_scene_comparison.py',
                    B/'scripts/run_wedetect_shot_entities.py']
    code_hashes = {str(p): sha(p) for p in source_paths}
    args = SimpleNamespace(out=case/'calls', codex_bin=codex_bin,
                           disabled_skills=io.disabled_skills_config(),
                           model='gpt-6-astra', reasoning='medium', timeout=timeout)
    transport.PROMPTS = B/'prompts'
    response = transport.call('registration_direct', prompt.name, payload, images, SCHEMA, args)
    fit = make_fit(response)
    for path, digest in {**hashes, **code_hashes}.items():
        if sha(path) != digest:
            raise ValueError('Direct registration source changed during inference: ' + path)
    status = read(call_dir/'status.json')
    result = dict(
        method='codex_direct', objective=None,
        selection='single direct model estimate; no optimization, candidate ranking or fallback',
        fit_population=None, independent_holdout=False,
        fits={'all_structures': fit},
        transform_model='positive scale + gravity-axis yaw + 3D translation, Shot3 to Shot1',
        geometric_diagnostics=fit['geometric_diagnostics'],
        reprojection_metrics_role='unavailable: no RoMA matching performed',
        model=args.model, reasoning=args.reasoning, model_call=str(call_dir),
        model_seconds=status['seconds'], usage=status['usage'],
        allocation=allocation, seconds=time.time()-started, source_case=str(case),
        input_hashes=hashes, source_hashes=code_hashes, inference_reuse=False,
        evidence_policy=dict(original_image_bytes_verified=True,
                             cross_shot_matching_supplied=False, anchors_supplied=False,
                             roma_supplied=False, previous_transform_supplied=False,
                             numerical_optimization=False),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    io.dump(call_dir/'transform.json', response)
    io.dump(call_dir/'source_audit.json', dict(passed=True, input_hashes=hashes, source_hashes=code_hashes,
                                             registration_path=str(output), registration_sha256=sha(output)))
    print(json.dumps(dict(output=str(output), seconds=result['seconds'], model_seconds=result['model_seconds'],
                          usage=result['usage'], scale=fit['scale'], yaw_deg=fit['yaw_deg'],
                          confidence=fit['confidence'])), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--codex-bin', default='/vast/users/guangyi.chen/.local/bin/codex')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    run(args.case, args.output, args.codex_bin, args.timeout)


if __name__ == '__main__':
    main()
