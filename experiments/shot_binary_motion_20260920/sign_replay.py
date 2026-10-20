"""Fix-only verifier replay: original local evidence, identities and geometry frozen."""
import sys,copy,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save,prepare_pair
from gs_boundary_spatial_review import review_spatial
from gs_temporal_core import aggregate
from run_isolated_shot_static_3d import owned_compute_job

def one(name):
    src=R/'production_replay'/name;dst=R/'sign_transport_fix'/name;dst.mkdir(parents=True,exist_ok=False)
    for pattern in ['narrative.json','runtime_profile.json','alignment_method.json','inputs/*.json','selected/*.json','expected_motion/*.json']:
        for p in src.glob(pattern):
            t=dst/p.relative_to(src);t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,t)
    for folder in ['pi3x','within']:(dst/folder).symlink_to((src/folder).resolve(),target_is_directory=True)
    prepare_pair(dst,'pair_000',['shot1','shot3']);pair=dst/'pairs/pair_000';old=src/'pairs/pair_000'
    for name2 in ['matching.json','matching_initial.json','identity_review.json']:
        shutil.copy2(old/name2,pair/name2)
    (pair/'registration').symlink_to((old/'registration').resolve(),target_is_directory=True)
    stage=Stage(pair,'temporal_binary_v1');stage.runtime['temporal_parallel_local_spatial']=False
    real=stage.call;hashes={}
    def call(name2,prompt,payload,images,schema):
        if name2.startswith('boundary_local_'):
            d=old/'calls'/name2
            canonical=dict(payload,images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=f['image_size']) for i,f in enumerate(images)])
            assert read(d/'input.json')==canonical,'Frozen local input changed'
            for f in ['input.json','response.json','prompt.txt']:
                hashes[str(d/f)]=hashlib.sha256((d/f).read_bytes()).hexdigest()
            return read(d/'response.json')
        return real(name2,prompt,payload,images,schema)
    stage.call=call
    state=dict(status='running');save(dst/'downstream_status.json',state)
    try:
        graphs=[read(pair/'selected'/f'{sid}_scene.json') for sid in ('shot1','shot3')]
        image_lists=[stage.source_images(sid)[1] for sid in ('shot1','shot3')]
        proposals=read(old/'boundary/proposals.json');save(pair/'boundary/proposals.json',proposals)
        original=read(old/'boundary/results.json');presence_checks={e['event_id']:e for e in original['events'] if e['kind']=='presence'}
        presence={e['group_id']:e['status'] for e in presence_checks.values()}
        spatial=review_spatial(stage,graphs,read(pair/'matching.json'),proposals,read(pair/'registration/roma_geometry/registration.json'),image_lists,presence)
        result=copy.deepcopy(original);result['spatial']=aggregate(proposals['spatial_units'],spatial,spatial=True)
        result['events']=list(presence_checks.values())+list(spatial.values())
        result['local_sign_transport']='raw subject/order/prose unchanged; separately labeled canonical relation'
        save(pair/'boundary/results.json',result)
        # The fix changes representation, not a single eligibility/gate/sign result.
        before=read(old/'boundary/local_support.json');after=read(pair/'boundary/local_support.json')
        for eid in before:
            for key in ['common_support_eligible','opposite_supported','local_axis_evidence']:
                assert before[eid][key]==after[eid][key],(eid,key)
        save(pair/'boundary/frozen_evidence_audit.json',dict(source=str(old),local_call_input_exact=True,local_evidence_hashes=hashes,
             all_numeric_axis_signs_and_evidence_gates_unchanged=True,only_final_verifier_rerun=True))
        state['status']='success';print(name,result['spatial']['summary'],flush=True)
    except BaseException as e:
        state.update(status='failed',error=repr(e));print(name,repr(e),flush=True)
    finally:save(dst/'downstream_status.json',state)
    return state

if __name__=='__main__':
    owned_compute_job()
    with ThreadPoolExecutor(max_workers=3) as pool:save(R/'sign_fix_summary.json',list(pool.map(one,['study2','study3','study4'])))
