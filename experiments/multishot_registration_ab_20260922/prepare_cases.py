import json,hashlib,shutil,time
from pathlib import Path
import imageio_ffmpeg
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parent; B=R.parents[1]; W=B/'experiments/wan_generation_400_20260921'
read=lambda p:json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
choices=[('parking4','7M9pU29bOeY_s00004_n4_clean_v2','Repeated car/pillar, wide-close-reverse-wide; shared structures'),('bedroom4','_6fzoABYwyk_s00021_n4_clean_v2','Doorway/bed alternating; nonadjacent recurrence and weak overlap'),('diner8','hERyYjy3O3U_s00003_n8_clean_v3_alt8','Eight-shot alternating booth, recurring people/table/window/seat')]
queue=read(W/'queue.json');tasks={t['key']:t for t in queue['tasks']};sources={e['episode_id']:e for e in map(json.loads,(W/'prompt_revision_20260922/input_queue_400.v2.jsonl').read_text().splitlines())}
rows=[]
for name,eid,why in choices:
 D=R/'inputs'/name;D.mkdir(parents=True,exist_ok=False);source=sources[eid];V=W/'videos'/eid;shots=[];vids=[];panels=[]
 assert len({s['scene_id'] for s in source['shots']})==1
 for s in source['shots']:
  sid=s['shot_id'];p=V/(sid+'.mp4');meta=read(V/(sid+'.json'));assert sha(p)==meta['sha256'];assert tasks[eid+'/'+sid]['status']=='done';assert tasks[eid+'/'+sid]['prompt_sha256']==s['wan_sha256']==meta['prompt_sha256'];assert sha(V/(sid+'.prompt.txt'))==s['wan_sha256']
  reader=imageio_ffmpeg.read_frames(str(p),input_params=['-threads','1'],output_params=['-threads','1']);probe=next(reader);w,h=probe['size'];frames=[];count=0
  for fid,data in enumerate(reader):
   count+=1
   if fid not in [0,16,32,48,64,80]:continue
   dest=D/'frames'/sid/f'frame_{fid:06d}.jpg';dest.parent.mkdir(parents=True,exist_ok=True);im=Image.frombytes('RGB',(w,h),data);im.save(dest,quality=95,subsampling=0)
   frames.append(dict(frame_id=fid,timestamp_sec=fid/probe['fps'],path=str(dest),sha256=sha(dest)))
   if fid==0:panels.append((sid,im.copy()))
  assert count==81 and len(frames)==6
  shots.append(dict(shot_id=sid,scene_id=s['scene_id'],frames=frames));vids.append(dict(shot_id=sid,path=str(p),sha256=sha(p),decoded_frames=count))
 save(D/'manifest.json',dict(shots=shots));save(D/'narrative.json',dict(facts=[dict(fact_id=s['shot_id'],shot_id=s['shot_id'],text=s['wan_prompt_en']) for s in source['shots']]))
 save(D/'wan_input.json',source);row=dict(name=name,episode_id=eid,reason=why,shots=len(shots),source_videos=vids,source_episode=str(V/'episode.mp4'),scene_id=source['shots'][0]['scene_id']);rows.append(row);save(D/'selection.json',row)
 canvas=Image.new('RGB',(832*2,510*((len(panels)+1)//2)),'white');draw=ImageDraw.Draw(canvas)
 for i,(sid,im) in enumerate(panels):x=i%2*832;y=i//2*510;draw.text((x+8,y+6),sid,fill='black');canvas.paste(im,(x,y+30))
 canvas.save(D/'overview.jpg',quality=95)
save(R/'selection.json',dict(selected_before_registration=True,episodes=rows,frames_per_shot=6,shared_frontend=True,production_changed=False))
print('prepared',[(r['name'],r['shots']) for r in rows],flush=True)
