from pipeline_io import *
from datetime import datetime,timezone
m=read(); checks=[]
def check(name,fn):
 try:fn();checks.append(dict(requirement=name,result='pass'))
 except Exception as e:checks.append(dict(requirement=name,result='fail',evidence=str(e)));raise
assert sha(m['source']['path'])==m['source']['sha256']
ids=[a['id'] for a in m['assets']]+[an['id'] for a in m['assets'] for an in a['anchors']];assert len(set(ids))==len(ids)
iids=[i['id'] for i in images(m)];assert len(set(iids))==len(iids)
for im in images(m):
 assert im['status']=='accepted',im['id']
 assert sha(im['path'])==im['sha256']
 pic=Image.open(im['path']);pic.load();assert pic.format=='PNG';assert list(pic.size)==im['size_px']
 if im['id'].startswith('shot_'):assert list(pic.size)==m['settings']['frame_size_px']
 assert P.joinpath(im['prompt_path']).read_text().strip()
 rs=[r for r in m['reviews'] if r['image_id']==im['id'] and r['decision']=='accept'];assert rs
 r=rs[-1];assert sha(r['candidate_path'])==r['candidate_sha256']==im['sha256'];assert r['reference_images']==im['reference_images']
 assert all(c['result']=='pass' for c in r['checks'])
 assert P.joinpath(r['prompt_path']).read_text()==P.joinpath(im['prompt_path']).read_text()
 for ref in im['reference_images']:assert sha(ref['path'])==ref['sha256']
for n,s in enumerate(m['shots'],1):
 assert s['id']==f'shot_{n}' and s['duration_seconds']==5
 assert P.joinpath(s['prompt_path']).read_text().startswith(f'Shot {n},')
 for f in s['frames'].values():
  for e in f['entities']:assert e['asset_id'] in ids
  for r in f['relations']:assert r['subject'] in ids and r['object'] in ids
for c in m['changes']:
 assert c['from'] in iids and c['to'] in iids
 assert all(e in ids for e in c['entity_ids'])
def paths(o):
 if isinstance(o,dict):
  for k,v in o.items():
   if k in ['path','prompt_path','candidate_path'] and isinstance(v,str):
    p=pathlib.Path(v);assert not p.is_absolute() and '..' not in p.parts;assert p.is_file()
   else:paths(v)
 elif isinstance(o,list):
  for v in o:paths(v)
paths(m)
events=[json.loads(x) for x in P.joinpath('generation_timing.jsonl').read_text().splitlines()];assert len(events)==22
for id in iids:
 es=[e for e in events if e['image_id']==id];assert [e['event'] for e in es]==['start','finish'];assert es[1]['generation_seconds']>0
assert not m['blockers']
report=dict(status='pass',checked_at=datetime.now(timezone.utc).isoformat(),accepted_images=len(iids),shots=3,frame_size_px=m['settings']['frame_size_px'],source_hash_verified=True,canonical_and_candidate_hashes_verified=True,reference_hashes_verified=True,prompts_verified=True,ids_relationships_and_paths_verified=True,timing_events_verified=len(events),generation_seconds=sum(e.get('generation_seconds',0) for e in events))
P.joinpath('verification_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
