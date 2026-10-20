import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
rows=[]
for path in sorted((R/'runs').glob('*/*/*/result.json')):
 d=read(path)
 if d['status']!='success':continue
 response=read(path.parent/'calls/identity_review/response.json');p=read(path.parent/'canonical_input.json');ims=read(path.parent/'images.json')
 actual={(im['shot_id'],im['frame_id']) for im in ims if im['shot_id']!='aligned_diagnostic'}
 groups={g['group_id']:g for g in response['matching']['groups']};checks=[]
 for rev in response['initial_group_reviews']:
  paired=any(groups[g]['identity']=='matched' for g in rev['result_group_ids']) or rev['action']=='split'
  ws=rev['witnesses'];shots={w['shot_id'] for w in ws};counts={s:len({w['frame_id'] for w in ws if w['shot_id']==s}) for s in ['shot1','shot3']}
  checks.append(dict(group=rev['initial_group_id'],action=rev['action'],paired_or_split=paired,has_both_shot_witnesses=shots=={'shot1','shot3'},frame_counts=counts,all_witness_frames_actually_attached=all((w['shot_id'],w['frame_id']) in actual for w in ws),explanation_nonempty=bool(rev['visual_identity_evidence'].strip())))
 rows.append(dict(study=d['study'],variant=d['variant'],repeat=d['repeat'],checks=checks,both_shot_witness_violations=[c['group'] for c in checks if c['paired_or_split'] and not c['has_both_shot_witnesses']],all_witness_frames_attached=all(c['all_witness_frames_actually_attached'] for c in checks),original_image_bytes_preserved=all(hashlib.sha256(Path(im['path']).read_bytes()).hexdigest()==im['sha256'] for im in ims)))
(R/'evidence_audit.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:print({k:v for k,v in r.items() if k!='checks'})
