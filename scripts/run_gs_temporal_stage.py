#!/usr/bin/env python3
"""Expected motion, within-shot review and boundary review; CPU/API stages."""
import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from gs_runtime_profile import profile
from gs_temporal_contract import EXPECTATION, REVIEW, PRESENCE_REVIEW, validate_expectation
from gs_temporal_core import within_proposals, boundary_proposals, aggregate
from gs_temporal_review import validate_checks

B = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


class Stage:
    def __init__(self, case, runtime_name=None):
        import run_wedetect_shot_entities as io
        self.case = Path(case).resolve(); self.runtime = profile(runtime_name)
        self.story = read(self.case/'narrative.json')
        self.scheduling = read(self.case/'scheduling.json') if (self.case/'scheduling.json').is_file() else {}
        self.args = SimpleNamespace(out=self.case/'calls',model=self.runtime['model'],
            reasoning=self.runtime['reasoning'],codex_bin='/vast/users/guangyi.chen/.local/bin/codex',
            timeout=1800,disabled_skills=io.disabled_skills_config())

    def call(self, name, prompt, payload, images, schema):
        import run_partial_scene_comparison as transport
        transport.PROMPTS = B/'prompts/gs_flow1'
        # Fresh outputs only. Replays require a fresh case and explicit upstream provenance.
        payload=dict(payload, images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=f['image_size']) for i,f in enumerate(images)])
        family = ('expectation' if name.startswith('expected_motion_') else
                  'within' if name.startswith('within_') else
                  'boundary_presence' if name.startswith('boundary_review_') else
                  'boundary_spatial' if name.startswith('boundary_local_') or name == 'boundary_spatial_verify' else None)
        choice = self.runtime.get('temporal_call_profiles', {}).get(family, {})
        mode = choice.get('transport', self.runtime.get('temporal_transport', 'canonical'))
        args = copy.copy(self.args)
        args.reasoning = choice.get('reasoning', self.args.reasoning)
        if mode == 'efficient':
            from gs_efficient_transport import call
            return call(name, str(transport.PROMPTS / prompt), payload, images, schema, args)
        if mode == 'compact':
            from gs_flow1_compact_transport import call
            return call(name, str(transport.PROMPTS / prompt), payload, images, schema, args)
        if mode != 'canonical':
            raise ValueError('Unknown temporal transport: ' + mode)
        return transport.call(name, prompt, payload, images, schema, args)

    def review_events(self, name, payload, images):
        events=payload['events']; checks=[]
        focused=name.startswith('boundary_review') and self.runtime.get('boundary_presence_protocol')=='presence_scoring_v1'
        if focused and any(e['kind']!='presence' for e in events):raise ValueError('Presence-only call received spatial event')
        prompt='boundary_presence_scoring_v1.txt' if focused else 'temporal_review_v2.txt'
        schema=PRESENCE_REVIEW if focused else REVIEW
        for offset in range(0,len(events),32):
            part=dict(payload,events=events[offset:offset+32])
            raw=self.call(name+f'_{offset//32:03d}',prompt,part,images,schema)
            if [r['event_id'] for r in raw['checks']] != [e['event_id'] for e in part['events']]:
                raise ValueError('Review batch changed event coverage/order')
            checks.extend(raw['checks'])
        return dict(checks=checks,limitations='All events reviewed in bounded batches; no proposal pruning')

    def source_images(self, sid):
        source = read(self.case/'inputs'/f'{sid}.json')
        images = [dict(f, shot_id=sid, image_size=size) for f,size in zip(source['frames'],source['image_sizes'])]
        return source, images

    def own_story(self, sid):
        facts = self.story['facts']
        selected = [f for f in facts if (not f.get('shot_id') or f['shot_id']==sid)
                    and (not f['fact_id'].startswith('shot') or f['fact_id']==sid)]
        if not selected:
            raise ValueError('No applicable normal prompt facts for '+sid)
        return dict(facts=selected, scope='normal prompt only; no other-shot actual evidence')

    def expectation(self, sid):
        from build_three_method_static_scenes import candidate_rows, fuse_rows
        src, images = self.source_images(sid)
        root = self.case/'pi3x'/sid; geom = read(root/'complete.json')
        frames = [read(root/'boxer_depth'/f'frame_{f["frame_id"]:06d}.json') for f in src['frames']]
        cameras = {f['frame_id']:f['camera'] for f in frames}
        pred = {f['frame_id']:{e['entity_id']:dict(geometry=e['geometry'],confidence=e['confidence'],
                 source_group=f'{sid}/{e["entity_id"]}/frame{f["frame_id"]}') for e in f['entities']} for f in frames}
        entities=[]
        for source in src['entities']:
            e=dict(source,local_id=source['entity_id'],entity_id=sid+'/'+source['entity_id'])
            entities.append(dict(entity_id=e['entity_id'],name=e['name'],observations=source['observations'],
                                 frame_evidence=candidate_rows(e,pred,cameras)))
        payload=dict(shot_id=sid,frames=[{k:f[k] for k in ('frame_id','timestamp_sec','sha256')} for f in images],
                     cameras=list(cameras.values()),entities=entities,normal_story_prompt=self.own_story(sid))
        from gs_shot_motion import PROTOCOL, SCHEMA, classification_payload, validate, node_fields
        protocol = self.runtime.get('expected_motion_protocol', 'interval_v2')
        if protocol not in ('interval_v2', PROTOCOL):
            raise ValueError('Unknown expected motion protocol: '+protocol)
        binary = protocol == PROTOCOL
        if binary:
            save(self.case/'expected_motion/inputs'/f'{sid}_full.json', payload)
            wire = classification_payload(payload)
            raw = self.call('expected_motion_'+sid, 'shot_motion_binary_v1.txt', wire, images, SCHEMA)
            validate(raw, wire)
        else:
            raw=self.call('expected_motion_'+sid,'expected_motion_v2.txt',payload,images,EXPECTATION)
            validate_expectation(raw,payload)
        save(self.case/'expected_motion'/f'{sid}.json',raw)
        nodes=[]
        for e, verdict in zip(entities,raw['entities']):
            # Keep auxiliary fusion solely for the unchanged identity/registration interface.
            # Temporal/boundary scores always read frame_evidence directly.
            motion_for_fusion=verdict['motion_status'] if binary else verdict['observed_status']; rows=e['frame_evidence']
            box, info=fuse_rows(rows) if motion_for_fusion=='static' else (None,None)
            if box is None:
                valid=[r for r in rows if r.get('geometry')]
                best=max(valid,key=lambda r:r.get('raw_quality',0)) if valid else None
                box=best['geometry'] if best else None
                info=dict(status='representative_frame' if best else 'missing_geometry',
                          frame_id=best['frame_id'] if best else None,role='identity_registration_only')
            if binary:
                nodes.append(dict(entity_id=e['entity_id'], name=e['name'], **node_fields(verdict),
                                  geometry=box, aggregation=info, frame_evidence=rows))
                continue
            observed=verdict['observed_status']
            expected_states={r['expected'] for r in verdict['intervals']}
            expected_status='static' if expected_states=={'static'} else 'unknown' if 'unknown' in expected_states else 'reasonable_motion'
            # An unexpectedly displaced object is expected-static but is not a fixed anchor.
            motion='moving' if expected_status=='reasonable_motion' else expected_status
            nodes.append(dict(entity_id=e['entity_id'],name=e['name'],motion_status=motion,
                motion_status_role='expected reasonable motion; never actual-change exemption',
                anchor_observed_static=observed=='static' and expected_status=='static',
                observed_motion_status=observed,expected_motion_status=expected_status,
                expected_motion_intervals=verdict['intervals'],geometry=box,aggregation=info,frame_evidence=rows))
        graph=dict(schema_version='temporal_entity_scene_v2',shot_id=sid,method='pi3x_boxer_depth',
                   coordinate_system=dict(world_frame_id=geom['scene_frame_id'],origin='fixed own-shot scene cloud median',
                                          z_axis='arbitrary; no physical-up estimate' if geom.get('coordinate_mode')=='pi3x_native' else 'up',per_frame_camera_poses=True,scale=geom['scale']),
                   cameras=list(cameras.values()),entities=nodes,
                   **({'motion_classification_protocol':protocol} if binary else {}),
                   counts=dict(entities=len(nodes),expected_static=sum(e['motion_status']=='static' for e in nodes),
                               stable_anchor_candidates=None if binary else sum(e['anchor_observed_static'] for e in nodes)))
        save(self.case/'selected'/f'{sid}_scene.json',graph)
        save(self.case/'selected'/f'{sid}_static_scene.json',dict(graph,entities=[e for e in nodes if e['motion_status']=='static']))

    def within(self, sid, presence_only=False):
        graph=read(self.case/'selected'/f'{sid}_scene.json'); expected=read(self.case/'expected_motion'/f'{sid}.json')
        _,images=self.source_images(sid);story=self.own_story(sid)
        proposals=within_proposals(graph,expected);dest=self.case/'within'/sid
        presence_enabled = self.runtime.get('within_presence_review', True)
        if not presence_enabled:
            # Preserve raw observations, all spatial comparisons and stable event IDs.
            proposals['events']=[e for e in proposals['events'] if e['kind']!='presence']
            proposals['presence_units']=[]
        proposals['presence_evaluation_run']=presence_enabled
        if presence_only:
            proposals['events']=[e for e in proposals['events'] if e['kind']=='presence']
            proposals['spatial_units']=[]
        save(dest/'proposals.json',proposals)
        payload=dict(mode='within_shot',graph=graph,expected_motion=expected,
                     events=proposals['events'],normal_story_prompt=story)
        review_protocol=self.runtime.get('within_review_protocol','temporal_review_v2')
        if review_protocol=='negative_cosine_only_v1':
            if presence_enabled:raise ValueError('Spatial-only review requires within presence disabled')
            from gs_temporal_within_spatial import review
            save(dest/'canonical_review_input.json',payload)
            raw=review(self,sid,graph,proposals['events'],story,images)
        elif review_protocol=='temporal_review_v2':
            raw=self.review_events('within_'+sid,payload,images)
        else:
            raise ValueError('Unknown within review protocol: '+review_protocol)
        checks=validate_checks(raw,proposals,images,story)
        save(dest/'results.json',dict(protocol='temporal_v2',status='success',shot_id=sid,
            presence_evaluation_run=presence_enabled,
            presence_status='completed' if presence_enabled else 'not_evaluated_user_disabled',
            presence=aggregate(proposals['presence_units'],checks) if presence_enabled else None,
            spatial=None if presence_only else aggregate(proposals['spatial_units'],checks,spatial=True),events=list(checks.values())))

    def boundary(self, presence_only=False):
        graphs=[read(self.case/'selected'/f'{s}_scene.json') for s in ('shot1','shot3')]
        image_lists=[self.source_images(s)[1] for s in ('shot1','shot3')];images=sum(image_lists,[])
        matching=read(self.case/'matching.json');registration=read(self.case/'registration/roma_geometry/registration.json')
        proposals=boundary_proposals(graphs,matching,registration['fits']['all_structures'])
        if presence_only:
            proposals['events']=[e for e in proposals['events'] if e['kind']=='presence']
            proposals['spatial_units']=[]
        save(self.case/'boundary/proposals.json',proposals)
        presence_proposals=dict(proposals,events=[e for e in proposals['events'] if e['kind']=='presence'])
        payload=dict(mode='boundary',graphs=graphs,matching=matching,events=presence_proposals['events'],
                     endpoint_observations=proposals['endpoint_observations'],target_frames=proposals['target_frames'],
                     frozen_registration=registration,normal_story_prompt=self.story)
        relative=getattr(self,'runtime',{}).get('boundary_spatial_protocol')=='relative_geometry_v1'
        if relative:
            from gs_boundary_relative_review import collect_spatial, finish_spatial, review_spatial
        else:
            from gs_boundary_spatial_review import collect_spatial, finish_spatial, review_spatial
        parallel=getattr(self,'scheduling',{}).get('parallel_boundary',False) and not presence_only
        if parallel:
            from concurrent.futures import ThreadPoolExecutor
            # Both branches read frozen evidence and write distinct call folders.
            # No scores are finalized until presence has passed its original gates.
            with ThreadPoolExecutor(max_workers=2) as pool:
                presence_future=pool.submit(self.review_events,'boundary_review',payload,images)
                spatial_future=pool.submit(collect_spatial,self,graphs,matching,proposals,registration,image_lists)
                raw=presence_future.result()
                collected=spatial_future.result()
        else:
            raw=self.review_events('boundary_review',payload,images)
            collected=None
        checks=validate_checks(raw,presence_proposals,images,self.story,boundary=True,
            presence_only_schema=getattr(self,'runtime',{}).get('boundary_presence_protocol')=='presence_scoring_v1')
        presence={e['group_id']:checks[e['event_id']]['status'] for e in presence_proposals['events']}
        if parallel:
            checks.update(finish_spatial(self,collected,proposals,image_lists,presence))
        else:
            checks.update(review_spatial(self,graphs,matching,proposals,registration,image_lists,presence))
        save(self.case/'boundary/results.json',dict(protocol='temporal_v2',status='success',
             spatial_review_protocol='relative_geometry_v1' if relative else 'flow1_original_prompts_endpoint_targets_all_keyframe_evidence_v1',
             target_frames=proposals['target_frames'],population='all reviewed identities; no motion exclusion',
             presence=aggregate(proposals['presence_units'],checks),
             spatial=None if presence_only else aggregate(proposals['spatial_units'],checks,spatial=True),events=list(checks.values())))


def remap(value, mapping):
    if isinstance(value,dict):
        return {k:remap(v,mapping) for k,v in value.items()}
    if isinstance(value,list):
        return [remap(v,mapping) for v in value]
    if isinstance(value,str):
        for old,new in mapping.items():
            if value==old:return new
            if value.startswith(old+'/'):return new+value[len(old):]
    return value


def prepare_pair(case, pair_id, shot_ids):
    """Explicit pair-local aliases for the unchanged two-shot geometry adapter."""
    dest=case/'pairs'/pair_id
    if dest.exists():raise FileExistsError(dest)
    mapping=dict(zip(shot_ids,('shot1','shot3')));dest.mkdir(parents=True)
    save(dest/'pair_scope.json',dict(original_shot_ids=shot_ids,aliases=mapping,order='manifest chronological scene occurrences'))
    for old,new in mapping.items():
        for folder,suffix in [('inputs','.json'),('selected','_scene.json'),('selected','_static_scene.json')]:
            save(dest/folder/(new+suffix),remap(read(case/folder/(old+suffix)),mapping))
        (dest/'pi3x').mkdir(exist_ok=True)
        (dest/'pi3x'/new).symlink_to((case/'pi3x'/old).resolve(),target_is_directory=True)
    story=copy.deepcopy(read(case/'narrative.json'))
    story['pair_alias_mapping']=dict(original_to_local=mapping,semantics='Local aliases apply to graph/image shot IDs only; original story shot names retain their original meaning. This metadata is not a motion-authorizing prompt fact.')
    save(dest/'narrative.json',story)
    for name in ('runtime_profile.json','alignment_method.json'):
        save(dest/name,read(case/name))
    if (case/'scheduling.json').is_file():
        save(dest/'scheduling.json',read(case/'scheduling.json'))
    hashes={str(p.resolve()):__import__('hashlib').sha256(p.read_bytes()).hexdigest()
            for sid in shot_ids for p in [case/'inputs'/f'{sid}.json',case/'selected'/f'{sid}_scene.json']}
    save(dest/'pair_input_hashes.json',hashes)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path)
    p.add_argument('stage',choices=['expectation','within','prepare_pair','boundary'])
    p.add_argument('--presence-only',action='store_true');p.add_argument('--shot');p.add_argument('--pair-id');p.add_argument('--shots',nargs=2);p.add_argument('--runtime-profile')
    a=p.parse_args()
    from run_isolated_shot_static_3d import owned_compute_job
    owned_compute_job()
    if a.stage=='prepare_pair':prepare_pair(a.case.resolve(),a.pair_id,a.shots)
    elif a.stage=='boundary':Stage(a.case,a.runtime_profile).boundary(a.presence_only)
    else:
        if not a.shot:raise ValueError('A single shot must be specified')
        stage=Stage(a.case,a.runtime_profile)
        if a.stage=='within':stage.within(a.shot,a.presence_only)
        else:stage.expectation(a.shot)


if __name__=='__main__':main()
