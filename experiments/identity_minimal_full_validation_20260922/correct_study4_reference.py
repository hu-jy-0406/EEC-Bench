"""Correct text-only schedule omission; retain original compiled reference/results."""
import sys,copy
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_prompt_alignment import read,save,freeze
c=copy.deepcopy(read(R/'references/study4/contract.json'));e=next(e for e in c['registry']['entities'] if e['prompt_entity_id']=='door')
e['schedule'][1]=dict(shot_id='shot2',expectation='required',reason='Shot2 explicitly begins near the visible doorway and tracks until it exits the right edge.')
e['evidence'].append(dict(fact_id='shot2',quote='Start near the open garden doorway'))
def claim(cid,dim,entities,predicate,expected,frame,quantifier,quote,deps):
 return dict(claim_id=cid,dimension=dim,entity_ids=entities,shot_ids=['shot2'],predicate=predicate,expected=expected,coordinate_frame=frame,quantifier=quantifier,depends_on=deps,evidence=[dict(fact_id='shot2',quote=quote)])
c['claims'] += [claim('fix_door_presence','presence',['door'],'present','镜头开场花园门口出现','none','exists','Start near the open garden doorway',[]),claim('fix_start_near_door','spatial',['woman','door'],'near','女子开场位于花园门口附近','world','start','Start near the open garden doorway',['p11','fix_door_presence']),claim('fix_door_exit_right','spatial',['door'],'outside_right_edge_at_end','结尾门口移至画面右边缘之外','screen','end','the doorway moves out of the right edge by the ending image',['fix_door_presence']),claim('fix_visible_door_open','spatial',['door'],'open','门在可见时处于打开状态','world','when_visible','open garden doorway',['fix_door_presence'])]
c['excluded_requirements']=[x for x in c['excluded_requirements'] if not x.startswith('shot2 的 door 注册为 not_required')]
c['claims_source']='Text-only compiler plus documented source-grounded door schedule correction; no video verdict consulted.'
out=R/'references/study4_corrected';freeze(c,out)
save(R/'reference_correction.json',dict(reason='Source text explicitly shows doorway at Shot2 start and exits right edge; initial authored schedule omitted this required occurrence.',video_evidence_used=False,original_retained=str(R/'references/study4'),corrected=str(out),added_claim_ids=[q['claim_id'] for q in c['claims'][-4:]],score_outcomes_used=False))
print(out)
