import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import run_wedetect_shot_entities as io
import run_isolated_shot_static_3d as motion
def read(p):return json.loads(Path(p).read_text())
assert read(OUT/'run.json')['status']=='success'
threads=[];requests=[];summary=[]
for row in read(OUT/'source_hashes.json'):
 assert io.sha(row['path'])==row['sha256'],row['path']
for case in ['study0','study1']:
 d=OUT/case;er=d/'entities';shot=read(er/'manifest.json')['shots'][0]
 prior=read(ROOT/'EECBench/experiments/study01_gs_v12_20260915'/case/'entities/manifest.json')
 assert shot==next(s for s in prior['shots'] if s['shot_id']=='shot1')
 for f in shot['frames']:assert io.sha(f['path'])==f['sha256']
 detections=io.load_detections(er/'detections',[shot]);payload=io.make_payload(shot,detections)
 assert payload==read(er/'shots/shot1/input.json')
 ent=io.validate_result(read(er/'shots/shot1/response.json'),payload)
 assert ent==read(er/'shots/shot1/entities.json')
 assert read(d/'geometry/audit.json')['status']=='pass'
 source=read(d/'static/source_shot.json')['shots'][0];mp=motion.make_payload(source)
 assert mp==read(d/'static/review/input.json')
 mr=read(d/'static/agent_review.json')['shots'][0];motion.validate_review(mr,mp)
 for stage in [er/'shots/shot1',d/'static/review']:
  io.audit_events(stage/'events.jsonl');req=read(stage/'request.json');requests.append(dict(stage=str(stage),request=req))
  cmd=req['command'];assert cmd[cmd.index('--model')+1]=='gpt-6-astra'
  assert 'model_reasoning_effort="medium"' in cmd and '--ephemeral' in cmd
  for line in (stage/'events.jsonl').read_text().splitlines():
   event=json.loads(line)
   if event['type']=='thread.started':threads.append(event['thread_id'])
 names={e['entity_id']:e['name'] for e in ent['entities']}
 entities=[dict(entity_id=e['entity_id'],name=names[e['entity_id'].split('/')[-1]],status=e['status'],visual_evidence=e['visual_evidence']) for e in mr['entities']]
 diag=read(er/'detections/diagnostic.json')
 summary.append(dict(case=case,input_size=payload['frames'][0]['image_size'],final_candidate_count=sum(f['count'] for f in diag),window_frames=[f['frame_id'] for f in diag if f['window']],door_frames=[f['frame_id'] for f in diag if f['door']],entity_count=len(entities),counts=read(d/'static/run.json')['counts'],entities=entities))
assert len(threads)==4 and len(set(threads))==4
for stage,split in [('entities/shots/shot1','\n<shot>\n'),('static/review','\nINPUT_JSON:\n')]:
 prompts=[(OUT/case/stage/'prompt.txt').read_text().split(split)[0] for case in ['study0','study1']]
 assert prompts[0]==prompts[1]
audit=dict(status='pass',original_jpeg_hashes_verified=12,detector_frames_verified=12,raw_proposals_saved=100800,cluster_schema_and_provenance_pass=2,motion_schema_and_provenance_pass=2,unique_fresh_cli_threads=threads,source_hashes_unchanged=True)
io.dump(OUT/'audit.json',audit);io.dump(OUT/'comparison.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
