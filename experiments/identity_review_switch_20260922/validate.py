"""CPU-only routing regression on frozen evidence plus two real production calls."""
import copy,json,os,shutil,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
R=Path(__file__).resolve().parent;B=R.parents[1];S=B/'scripts';sys.path[:0]=[str(S),str(B/'tests')]
from run_gs_integrated import read,save,sha
import review_aligned_entity_identities as review
from gs_identity_review_minimal_input import build
from gs_runtime_profile import profile
from gs_entity_appearance_compact import cost
BASES=read(B/'experiments/gravity_free_pipeline_20260921/baselines.json')

def prepare(study,mode,kind):
    source=Path(BASES[study])/'pairs/pair_000';case=R/kind/(study+'_'+mode);case.mkdir(parents=True,exist_ok=False)
    for name in ('inputs','selected'):shutil.copytree(source/name,case/name)
    for name in ('narrative.json','matching_initial.json'):
        shutil.copy2(source/name,case/name)
    shutil.copy2(source/'matching_initial.json',case/'matching.json')
    dest=case/'registration/roma_geometry/registration.json';dest.parent.mkdir(parents=True);shutil.copy2(source/'registration/roma_geometry/registration.json',dest)
    # Emulate the integrated runner's saved, resolved runtime.
    runtime=profile();runtime['identity_review_input']=mode;save(case/'runtime_profile.json',runtime)
    return source,case

env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join([str(S),str(B/'tests')])
with (R/'tests.log').open('w') as log:
    proc=subprocess.run([sys.executable,'-m','unittest','test_gs_identity_review_switch','test_gs_scoring_efficiency','test_gs_integrated','test_gs_temporal','test_gs_all_entity_identity','-v'],env=env,stdout=log,stderr=subprocess.STDOUT)
print('TESTS',proc.returncode,flush=True)
if proc.returncode:raise RuntimeError('Tests failed: '+str(R/'tests.log'))
rows=[]
for study in BASES:
    response=read(B/'experiments/identity_minimal_full_validation_20260922/runs'/study/'pairs/pair_000/identity_review.json')
    for mode in ('minimal','full'):
        source,case=prepare(study,mode,'frozen_routing')
        args=SimpleNamespace(out=case/'calls',model='gpt-6-astra',reasoning='medium',identity_review_input=mode,identity_review_protocol=review.FOCUSED_PROTOCOL)
        original=read(source/'identity_review_payload.json')
        def call(stage,prompt,payload,images,schema,args):
            canonical=read(case/'identity_review_payload.json')
            assert canonical==original,'Canonical evidence changed'
            if mode=='full':
                assert payload==original and len(images)==len(original['images'])+1
                assert prompt=='gs_aligned_identity_scoring_v1.txt'
            else:
                expected,attachments=build(canonical,read(case/'identity_review_images.json'))
                assert payload==expected and images==attachments
                assert prompt=='gs_aligned_identity_minimal_v1.txt'
            for im in images:assert sha(im['path'])==im['sha256']
            save(case/'observed_request.json',dict(prompt=prompt,image_count=len(images),payload=payload))
            return copy.deepcopy(response)
        with patch.object(review.transport,'call',side_effect=call):review.run_case(case,args)
        assert read(case/'identity_review_audit.json')['passed']
        rows.append(dict(study=study,mode=mode,canonical_equal=True,original_images_verified=True,real_semantic_validation=True,recorded_response_reused=True))
save(R/'frozen_routing_audit.json',rows)
# Prompts and semantic validation function remain unchanged.
import ast
before=(R/'before/scripts/review_aligned_entity_identities.py').read_text();after=(S/'review_aligned_entity_identities.py').read_text()
get=lambda text:ast.dump(next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='validate'))
assert get(before)==get(after)
for prompt in ('gs_aligned_identity_review_v1.txt','gs_aligned_identity_scoring_v1.txt','gs_aligned_identity_minimal_v1.txt'):
    assert sha(R/'before/prompts'/prompt)==sha(B/'prompts'/prompt)
print('FROZEN ROUTING all 6 passed',flush=True)

def live(mode):
    source,case=prepare('study3',mode,'live')
    cmd=[sys.executable,str(S/'run_gs_flow1_stage.py'),str(case),'review_identity']
    # Default invocation exercises selected/saved minimal; rollback exercises CLI.
    if mode=='full':cmd+=['--identity-review-input','full']
    start=time.time()
    with (case/'stage.log').open('w') as log:proc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
    row=dict(mode=mode,command=cmd,returncode=proc.returncode,seconds=time.time()-start)
    status=read(case/'calls/identity_review/status.json') if (case/'calls/identity_review/status.json').exists() else {}
    usage=status.get('usage',status.get('known_usage',[]));row.update(usage=usage,total_tokens=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in usage),standard_api_equivalent_usd=cost(usage))
    save(case/'validation.json',row)
    if proc.returncode:raise RuntimeError('Production call failed: '+str(case/'stage.log'))
    manifest=read(case/'identity_review_request.json');assert manifest['identity_review_input']==mode
    request=read(case/'calls/identity_review/input.json');canonical=read(case/'identity_review_payload.json')
    assert canonical==read(source/'identity_review_payload.json')
    if mode=='full':assert request==canonical
    else:assert request==build(canonical,read(case/'identity_review_images.json'))[0]
    assert read(case/'identity_review_audit.json')['passed']
    result=read(case/'identity_review.json')['matching']
    row.update(image_count=len(manifest['images']),prompt=manifest['prompt'],canonical_equal=True,
               partitions=sorted([dict(identity=g['identity'],a=sorted(g['a_ids']),b=sorted(g['b_ids'])) for g in result['groups']],key=lambda g:(g['a'],g['b'])),
               anchors=result['structural_anchor_group_ids'],origin=result['local_origin_group_id'],reference=result['local_reference_group_id'])
    save(case/'validation.json',row);print('LIVE',mode,'success',row['total_tokens'],row['standard_api_equivalent_usd'],flush=True)
    return row
start=time.time()
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(live,('minimal','full')))
save(R/'live_validation.json',dict(calls=results,parallel_seconds=time.time()-start,total_tokens=sum(r['total_tokens'] for r in results),standard_api_equivalent_usd=sum(r['standard_api_equivalent_usd'] for r in results),partitions_equal=results[0]['partitions']==results[1]['partitions'],anchors_equal=all(results[0][k]==results[1][k] for k in ('anchors','origin','reference')),scope='Frozen upstream, fresh identity calls only; no full pipeline rerun'))
print('COMPLETE',flush=True)
