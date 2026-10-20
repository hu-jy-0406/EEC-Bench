import json,hashlib,subprocess,shutil
from pathlib import Path
from fractions import Fraction
import imageio_ffmpeg
from PIL import Image
R=Path(__file__).resolve().parent;B=R.parents[1];W=B/'experiments/wan_generation_400_20260921';eid='_6fzoABYwyk_s00021_n4_clean_v2';V=W/'videos'/eid;D=R/'test_case';D.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
queue=read(W/'queue.json');tasks={t['key']:t for t in queue['tasks']}
source=next(json.loads(l) for l in (W/'prompt_revision_20260922/input_queue_400.v2.jsonl').read_text().splitlines() if json.loads(l)['episode_id']==eid)
bundle=B/'exports/storymem_hf_priority50_20260922/storymem_inputs';entry=next(e for e in read(bundle/'index.json')['episodes'] if e['episode_id']==eid)
for key,name in [('contract_path','contract.json'),('entity_schedule_path','entity_schedule.json'),('alignment_contract_path','alignment_contract.json'),('story_script_path','story_script.json')]:shutil.copy2(bundle/entry[key],D/name)
save(D/'wan_input.json',source);sources={};shots=[];video_records=[];sample_ids=[0,16,32,48,64,80]
for s in source['shots']:
 sid=s['shot_id'];p=V/(sid+'.mp4');meta=read(V/(sid+'.json'));assert sha(p)==meta['sha256'];assert tasks[eid+'/'+sid]['status']=='done';assert tasks[eid+'/'+sid]['prompt_sha256']==s['wan_sha256']==meta['prompt_sha256'];assert sha(V/(sid+'.prompt.txt'))==s['wan_sha256']
 reader=imageio_ffmpeg.read_frames(str(p),input_params=['-threads','1'],output_params=['-threads','1'])
 probe=next(reader);fps=probe['fps'];width,height=probe['size'];assert fps==16 and (width,height)==(832,480)
 out=D/'frames'/sid;out.mkdir(parents=True);frames=[];count=0
 for fid,data in enumerate(reader):
  count+=1
  if fid not in sample_ids:continue
  dest=out/f'frame_{fid:06d}.jpg';Image.frombytes('RGB',(width,height),data).save(dest,quality=95,subsampling=0)
  frames.append(dict(frame_id=fid,timestamp_sec=fid/fps,path=str(dest.resolve()),sha256=sha(dest)))
 assert count==81 and len(frames)==6;probe['decoded_frames']=count
 shots.append(dict(shot_id=sid,scene_id=s['scene_id'],frames=frames))
 video_records.append(dict(shot_id=sid,video=str(p),sha256=sha(p),metadata=str(V/(sid+'.json')),probe=probe,preview=str(V/(sid+'.contact.jpg'))))
 sources[str(p)]=meta['sha256']
episode=read(V/'episode.json');assert sha(V/'episode.mp4')==episode['sha256'];sources[str(V/'episode.mp4')]=episode['sha256']
save(D/'manifest.json',dict(shots=shots))
save(D/'narrative.json',dict(facts=[dict(fact_id=s['shot_id'],shot_id=s['shot_id'],text=s['wan_prompt_en']) for s in source['shots']]))
save(D/'selection.json',dict(episode_id=eid,generation_priority=39,scene_id='Scene1',shot_count=4,video=str(V/'episode.mp4'),total_frames=324,actual_duration_seconds=324/16,prompt_target_duration_seconds=20,shot_videos=video_records,source_hashes=sources,keyframes_per_shot=6,sampled_frame_ids=sample_ids,scope='Wan2.2 generated pixels, not source film. Video hashes/probes and original prompt hashes verified. Frames decoded without crop/resize, saved JPEG quality95/subsampling0.',candidate_gap=dict(first='Shot2',intervening=['Shot3'],last='Shot4',objects=['orange bedside lamp','bed','question-mark print','plaid blanket']),detection_run=False,registration_run=False,identity_run=False,ground_truth_identity=False))
print('PREPARED',D,'24 native-resolution sampled JPEGs; all source videos and prompt hashes verified',flush=True)
