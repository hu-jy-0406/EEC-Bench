#!/usr/bin/env python3
"""One invocation, one fresh tool-free visual agent, one shot static graph."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import re
import time

import run_wedetect_shot_entities as io
import run_partial_scene_comparison as transport
import run_shot_static_3d as fusion

PROMPT = 'shot_motion_isolated_v0.2.txt'


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


INTS = dict(type='array', items=dict(type='integer'))
TEXT = dict(type='string')
SCHEMA = obj(dict(shot_id=TEXT, camera_assessment=TEXT, entities=dict(type='array', items=obj(dict(
    entity_id=TEXT, status=dict(type='string', enum=['static', 'moving', 'unknown']),
    visual_evidence=TEXT, image_box_evidence=TEXT, geometry_evidence=TEXT,
    reviewed_frame_ids=INTS, observed_frame_ids=INTS,
    motion_intervals=dict(type='array', items=INTS), uncertainty=TEXT)))))


def make_payload(shot):
    sid = shot['shot_id']
    images = shot['calibration']['images']
    frame_ids = [f['frame_id'] for f in images]
    if len(frame_ids) != 6 or len(set(frame_ids)) != 6 or frame_ids != sorted(frame_ids):
        raise ValueError('Exactly six unique chronological images required')
    if [f['frame_id'] for f in shot['frames']] != frame_ids:
        raise ValueError('Camera frame coverage mismatch')
    nodes = []
    entity_ids = [e['entity_id'] for e in shot['entities']]
    if len(set(entity_ids)) != len(entity_ids):
        raise ValueError('Duplicate entity IDs')
    for entity in shot['entities']:
        if not entity['entity_id'].startswith(sid + '/'):
            raise ValueError('Foreign entity in shot')
        if any([r['frame_id'] for r in entity[key]] != frame_ids for key in ('observations', 'states')):
            raise ValueError('Entity frame coverage mismatch')
        states = []
        for state in entity['states']:
            geometry = state['geometry']
            if geometry is not None:
                geometry = {key: geometry[key] for key in
                            ('center_world', 'size_xyz', 'R_world_from_object')}
            states.append(dict(frame_id=state['frame_id'], geometry=geometry))
        observations = [{key: row[key] for key in ('frame_id', 'exist', 'visible', 'box_xyxy')}
                        for row in entity['observations']]
        nodes.append(dict(entity_id=entity['entity_id'], name=entity['name'],
                          observations=observations, states=states))
    frames = [dict(frame_id=f['frame_id'], timestamp_sec=f['timestamp_sec'],
                   attachment_index=i+1, sha256=f['sha256']) for i, f in enumerate(images)]
    cameras = [{key:f[key] for key in ('frame_id', 'image_sha256', 'K',
                'R_world_from_camera', 'translation_world_from_camera')} for f in shot['frames']]
    return dict(shot_id=sid, frames=frames, world_frame_id=shot['world_frame_id'],
                observation_semantics='Null exist means unknown; false visible with a null box means no retained observation, not proof of absence or full occlusion.',
                scale=shot['scale'], camera_frames=cameras, entities=nodes)


def validate_review(review, payload):
    import jsonschema
    jsonschema.validate(review, SCHEMA)
    if review['shot_id'] != payload['shot_id']:
        raise ValueError('Wrong shot')
    if [e['entity_id'] for e in review['entities']] != [e['entity_id'] for e in payload['entities']]:
        raise ValueError('Entity coverage/order changed')
    frames = [f['frame_id'] for f in payload['frames']]
    for result, entity in zip(review['entities'], payload['entities']):
        if result['reviewed_frame_ids'] != frames:
            raise ValueError('All frames must be reviewed')
        visible = [o['frame_id'] for o in entity['observations'] if o['visible']]
        if result['observed_frame_ids'] != visible:
            raise ValueError('Observed frame coverage mismatch')
        for key in ('visual_evidence', 'image_box_evidence', 'geometry_evidence', 'uncertainty'):
            if not result[key].strip():
                raise ValueError('Missing evidence')
        if result['status'] == 'static' and result['motion_intervals']:
            raise ValueError('Static verdict conflicts with movement evidence')
        if result['status'] == 'moving' and not result['motion_intervals']:
            raise ValueError('Movement needs temporal evidence')
        for interval in result['motion_intervals']:
            if len(interval) != 2 or any(x not in frames for x in interval) or interval[0] >= interval[1]:
                raise ValueError('Invalid movement interval')


def owned_compute_job():
    job = os.environ.get('SLURM_JOB_ID', '')
    if not job.isdigit():
        raise RuntimeError('A current owned Slurm step is required')
    raw = subprocess.check_output(['scontrol', 'show', 'job', job, '-o'], text=True)
    fields = dict(x.split('=', 1) for x in raw.split() if '=' in x)
    uid = re.fullmatch(r'.*\((\d+)\)', fields.get('UserId', ''))
    if not uid or int(uid[1]) != os.getuid() or fields.get('JobState') != 'RUNNING':
        raise RuntimeError('Allocation not running or not owned by this UID')
    hosts = subprocess.check_output(['scontrol', 'show', 'hostnames', fields['NodeList']], text=True).splitlines()
    if socket.gethostname().split('.')[0] not in hosts:
        raise RuntimeError('Current host is outside owned allocation')
    return job


def run(args):
    job = owned_compute_job()
    if os.getloadavg()[0] > 8:
        raise RuntimeError('Node load too high for this small CPU pilot')
    source = io.read(args.source)
    selected = [s for s in source['shots'] if s['shot_id'] == args.shot]
    if len(selected) != 1:
        raise ValueError('Select exactly one known shot')
    shot = selected[0]
    payload = make_payload(shot)
    args.out.mkdir(parents=True, exist_ok=False)
    snapshot = dict(schema_version=source['schema_version'], shots=[shot])
    io.dump(args.out / 'source_shot.json', snapshot)
    images = [dict(f, shot_id=args.shot) for f in shot['calibration']['images']]
    for f in images:
        if io.sha(f['path']) != f['sha256']:
            raise ValueError('Changed image')
    args.disabled_skills = io.disabled_skills_config()
    started = time.time()
    state = dict(status='running', shot_id=args.shot, host=socket.gethostname(), allocation=job,
                 source_sha256=io.sha(args.source), started=started, model=args.model,
                 isolation='one fresh ephemeral CLI, empty cwd, disabled tools/skills/docs/memories; own six images only')
    io.dump(args.out / 'run.json', state)
    try:
        raw = transport.call('review', PROMPT, payload, images, SCHEMA, args)
        validate_review(raw, payload)
        review = dict(reviewer='fresh isolated configured Codex CLI', scope='single shot only', shots=[raw])
        io.dump(args.out / 'agent_review.json', review)
        graph = fusion.build(snapshot, review)
        provenance_paths = [args.out/'source_shot.json', args.out/'agent_review.json', Path(__file__),
                            Path(fusion.__file__), transport.PROMPTS/PROMPT]
        provenance_paths += [Path(f['path']) for f in images]
        graph['provenance'] = [dict(path=str(p.resolve()), sha256=io.sha(p)) for p in provenance_paths]
        io.dump(args.out / 'static_scene_graph.json', graph)
        (args.out/'viewer.html').write_text(fusion.viewer(graph))
        io.dump(args.out/'diagnostics.json', fusion.diagnostics(snapshot))
        state.update(status='success', counts={k:sum(e['status']==k for e in raw['entities'])
                     for k in ('static','moving','unknown')}, usage=io.read(args.out/'review/status.json')['usage'])
    except BaseException as exc:
        state.update(status='failed', error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        state.update(seconds=time.time()-started)
        io.dump(args.out/'run.json', state)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source', type=Path, default=fusion.SOURCE)
    p.add_argument('--shot', required=True)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--model', default='gpt-6-astra')
    p.add_argument('--reasoning', default='medium')
    p.add_argument('--codex-bin', default='codex')
    p.add_argument('--timeout', type=int, default=1800)
    args=p.parse_args();args.out=args.out.resolve();args.source=args.source.resolve()
    run(args)
