import json,hashlib
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent
p=json.loads((root/'pipeline.json').read_text())
checks=[]
def check(name,condition):
 checks.append({'requirement':name,'result':'pass' if condition else 'fail'})
 if not condition: raise AssertionError(name)
def path(s):
 f=root/s;check('Relative contained path: '+s,not Path(s).is_absolute() and f.resolve().is_relative_to(root));return f
 def_unused=None
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
check('Source preserved',sha(path(p['source']['path']))==p['source']['sha256'])
check('Verification and timing enabled',p['settings']['verification'] and p['settings']['timing'])
assets=p['assets'];shots=p['shots'];ims=[a['image'] for a in assets]+[f['image'] for s in shots for f in s['frames'].values()]
ids=[a['id'] for a in assets]+[x['id'] for a in assets for x in a['anchors']];iids=[x['id'] for x in ims]
check('Unique entity/anchor and image IDs',len(ids)==len(set(ids)) and len(iids)==len(set(iids)))
check('Three consecutive shots', [s['id'] for s in shots]==['shot_1','shot_2','shot_3'])
for im in ims:
 check('Accepted '+im['id'],im['status']=='accepted')
 f=path(im['path']);check('Canonical image hash '+im['id'],sha(f)==im['sha256'])
 with Image.open(f) as image:
  image.load();check('PNG decode and dimensions '+im['id'],image.format=='PNG' and list(image.size)==im['size_px'])
  if im['id'].startswith('shot_'):check('Shared scene dimensions '+im['id'],list(image.size)==p['settings']['frame_size_px'])
 check('Nonempty image prompt '+im['id'],bool(path(im['prompt_path']).read_text().strip()))
 accepted=[r for r in p['reviews'] if r['image_id']==im['id'] and r['decision']=='accept']
 check('Exactly one accepted review '+im['id'],len(accepted)==1)
 r=accepted[0];check('Accepted candidate matches canonical '+im['id'],sha(path(r['candidate_path']))==r['candidate_sha256']==im['sha256'])
 check('Accepted exact prompt '+im['id'],path(r['prompt_path']).read_bytes()==path(im['prompt_path']).read_bytes())
 check('Accepted references match actual call '+im['id'],r['reference_images']==im['reference_images'])
 check('All required image checks pass '+im['id'],all(c['result']=='pass' for c in r['checks']))
 for ref in im['reference_images']:check('Reference hash '+ref['path'],sha(path(ref['path']))==ref['sha256'])
for r in p['reviews']:
 check('Attempt within cap '+r['image_id'],1<=r['attempt']<=p['settings']['max_attempts_per_image'])
 check('Archived prompt '+r['image_id'],bool(path(r['prompt_path']).read_text().strip()))
 if r['candidate_path']:check('Historical candidate hash '+r['candidate_path'],sha(path(r['candidate_path']))==r['candidate_sha256'])
 for ref in r['reference_images']:check('Historical reference hash '+ref['path'],sha(path(ref['path']))==ref['sha256'])
for s in shots:
 check('Positive duration '+s['id'],s['duration_seconds']>0)
 check('Nonempty video prompt '+s['id'],bool(path(s['prompt_path']).read_text().strip()))
 for f in s['frames'].values():
  for e in f['entities']:check('Entity resolves '+e['asset_id'],e['asset_id'] in ids and not(e['presence']=='elsewhere' and e['visibility']=='visible'))
  for r in f['relations']:check('Relation resolves '+r['subject']+' '+r['object'],r['subject'] in ids and r['object'] in ids)
for c in p['changes']:check('Change endpoints resolve',c['from'] in iids and c['to'] in iids and all(x in ids for x in c['entity_ids']))
events=[json.loads(x) for x in (root/'generation_timing.jsonl').read_text().splitlines()]
starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event'] in ['finish','error']]
check('Each timed call has exactly one completion',len(starts)==len(ends) and len({(e['image_id'],e['attempt']) for e in starts})==len(starts))
for e in starts:
 m=[x for x in ends if (x['image_id'],x['attempt'])==(e['image_id'],e['attempt'])];check('Timed attempt completion',len(m)==1 and m[0]['generation_seconds']>=0)
check('Sequence accepted',p['sequence_review']['decision']=='accept' and all(c['result']=='pass' for c in p['sequence_review']['checks']))
check('No blockers',not p['blockers'])
report={'status':'pass','checks_passed':len(checks),'accepted_images':len(ims),'shots':len(shots),'duration_seconds':sum(s['duration_seconds'] for s in shots),'frame_size_px':p['settings']['frame_size_px'],'generation_calls':len(starts),'tool_errors':sum(e['event']=='error' for e in ends),'generation_seconds':round(sum(e['generation_seconds'] for e in ends),3),'checks':checks}
(root/'verification_report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
