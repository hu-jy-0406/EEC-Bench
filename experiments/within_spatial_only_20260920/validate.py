"""Frozen-output regression: no model calls; compares the unchanged spatial path."""
import json
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from run_gs_temporal_stage import Stage, read, save
from gs_runtime_profile import profile
from gs_temporal_core import within_proposals, aggregate
source = ROOT/'experiments/shot_binary_motion_20260920'
def canonical_reason(value):
    # Binary validation artifacts predate a wording-only diagnostic correction.
    if isinstance(value,dict):
        return {k: ('reasonable_motion_somewhere_in_shot' if k=='reason' and v=='reasonable_motion_between_frames' else canonical_reason(v)) for k,v in value.items()}
    if isinstance(value,list):return [canonical_reason(v) for v in value]
    return value
rows=[]
for study in ('study2','study3','study4'):
    original=source/study
    for sid in ('shot1','shot2','shot3'):
        old=read(original/'within'/sid/'results.json')
        reviews={e['event_id']: e['review'] for e in old['events']}
        full=within_proposals(read(original/f'selected/{sid}_scene.json'),read(original/f'expected_motion/{sid}.json'))
        historical_checks={e['event_id']:e for e in old['events']}
        original_presence=aggregate(full['presence_units'],historical_checks)
        original_spatial=aggregate(full['spatial_units'],historical_checks,spatial=True)
        assert original_presence['summary']==old['presence']['summary']
        assert canonical_reason(original_spatial)==canonical_reason(old['spatial'])
        for enabled, presence_only in ((False,False),(True,False),(False,True)):
            with tempfile.TemporaryDirectory() as tmp:
                stage=Stage.__new__(Stage)
                stage.case=Path(tmp);stage.story=read(original/'narrative.json')
                stage.runtime=dict(profile(), within_presence_review=enabled)
                for relative in (f'selected/{sid}_scene.json',f'expected_motion/{sid}.json',f'inputs/{sid}.json'):
                    save(stage.case/relative,read(original/relative))
                calls=[]
                def replay(name,prompt,payload,images,schema):
                    events=payload['events'];calls.append([e['event_id'] for e in events])
                    assert enabled or all(e['kind']=='spatial' for e in events)
                    return dict(checks=[reviews[e['event_id']] for e in events],limitations='Frozen model evidence; no API call')
                stage.call=replay
                stage.within(sid,presence_only=presence_only)
                result=read(stage.case/'within'/sid/'results.json')
                proposals=read(stage.case/'within'/sid/'proposals.json')
                assert result['presence_evaluation_run']==enabled
                assert result['presence']==(original_presence if enabled else None)
                assert result['spatial']==(None if presence_only else original_spatial)
                if not enabled:
                    assert proposals['presence_units']==[]
                    assert result['presence_status']=='not_evaluated_user_disabled'
                if presence_only: assert calls==[]
                if not enabled and not presence_only:
                    old_p=read(original/'within'/sid/'proposals.json')
                    assert canonical_reason(proposals['spatial_units'])==canonical_reason(old_p['spatial_units'])
                    assert result['events']==[e for e in old['events'] if e['kind']=='spatial']
                    rows.append(dict(study=study,shot=sid,spatial_events=len(result['events']),required_review_batches=len(calls),spatial_numbers_events_statuses_scores_equal=True))
assert profile()['within_presence_review'] is False
save(Path(__file__).with_name('validation.json'),dict(status='pass',cases=rows,stage_runs=27,new_model_calls=0,new_api_usd=0,scope='Deterministic frozen-review replay, not fresh model quality validation'))
print(json.dumps(rows,indent=2))
