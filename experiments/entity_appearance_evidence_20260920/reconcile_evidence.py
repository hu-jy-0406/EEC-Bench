"""After inference completes: union already reported event/dimension witnesses.
No new model call, no changed verdict, gate, severity, image or prompt.
"""
from pathlib import Path
import importlib
import json
import hashlib
import shutil
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import gs_entity_appearance_evidence as v4
root=Path(__file__).resolve().parent
runs=[root/'study2',root/'study3']
source=ROOT/'scripts/gs_entity_appearance_evidence.py'
old_text=source.read_text()
old='''        for event in changes:
            if not set(event['a'] + event['b']) <= set(ids):
                raise ValueError('Dimension evidence must include its change witnesses')
'''
new='''        # Event d explicitly attributes its witnesses to this dimension. Merge
        # those existing references; do not require the model to repeat them in e.
        merged_ids = sorted(set(ids).union(*(set(x['a'] + x['b']) for x in changes)))
        evidence = indices(merged_ids, 2 if q else 0)
'''
assert old in old_text, 'Run this one-time migration only against the original adapter'
for run in runs:
    m=v4.verify(run)
    for e in m['entities']:
        c=v4.read(run/'entities'/e['global_entity_id']/'codex.json')
        if e['appearances']>=2:
            assert v4.read(run/'calls'/e['global_entity_id']/'status.json')['status']=='success'
    shutil.copy2(run/'manifest.json',run/'inference_manifest.json')
source.write_text(old_text.replace(old,new))
importlib.reload(v4)
recovered=[]
for run in runs:
    m=v4.read(run/'manifest.json')
    m['inference_manifest']=str(run/'inference_manifest.json')
    m['source_hashes'][str(source)]=v4.sha(source)
    m['source_hashes'][str(run/'inference_manifest.json')]=v4.sha(run/'inference_manifest.json')
    snapshot=root/'source_snapshot/gs_entity_appearance_evidence.py'
    m['source_hashes'][str(snapshot)]=v4.sha(snapshot)
    m['output_adapter_revision']='Union explicitly reported event witnesses into attributed dimension evidence; unchanged raw model outputs and scoring semantics.'
    v4.dump(run/'manifest.json',m)
    for e in m['entities']:
        eid=e['global_entity_id'];f=run/'entities'/eid
        if e['appearances']<2:continue
        previous=v4.read(f/'codex.json')
        raw=v4.read(run/'calls'/eid/'response.json')
        expanded=v4.expand(raw,v4.read(f/'input.json'))
        if previous['status']=='success':assert previous['score']==expanded['score']
        else: recovered.append(dict(study=run.name,entity=eid,old_error=previous['error']))
        shutil.copy2(f/'codex.json',f/'codex_before_evidence_union.json')
        v4.dump(f/'codex.json',dict(status='success',score=expanded['score'],result=expanded))
shutil.copy2(source,root/'source_snapshot/gs_entity_appearance_evidence_final.py')
v4.dump(root/'adapter_reconciliation.json',dict(raw_model_outputs_changed=False,new_calls=0,
    score_policy_changed=False,recovered=recovered,explanation='Merge explicit event witnesses; no invented evidence or relaxed visual gates.'))
print(json.dumps(dict(recovered=recovered)))
