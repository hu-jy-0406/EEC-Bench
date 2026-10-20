from pathlib import Path
import json,time
from compact_payload import pack,unpack,dump,equivalent
H=Path(__file__).resolve().parent;E=H.parent
paths={'matching':E/'study2_full_fresh_20260918/study2/calls/matching/input.json','identity_review':E/'study2_identity_frozen_replay_20260919/calls/original/input.json','presence':E/'study2_flow2_separate_ab_20260919/flow1/calls/presence_1/input.json'}
result={}
for stage,p in paths.items():
 x=json.loads(p.read_text());t=time.time();w=pack(x);equivalent(x,unpack(w))
 result[stage]=dict(original_chars=len(dump(x)),wire_chars=len(dump(w)),ratio=len(dump(w))/len(dump(x)),seconds=time.time()-t,shared_count=len(w['shared']))
 (H/f'{stage}_wire_profile.json').write_text(dump(w)+'\n')
print(json.dumps(result,indent=2));(H/'payload_profile.json').write_text(json.dumps(result,indent=2)+'\n')
