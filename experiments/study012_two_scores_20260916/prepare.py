import json,hashlib,shutil,time
from pathlib import Path
from PIL import Image
HERE=Path(__file__).resolve().parent; EEC=HERE.parents[1]; OLD=EEC/'experiments/shot_scene_boxes_goal_20260916'
def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for case in ['study0','study1','study2']:
 out=HERE/case;out.mkdir(exist_ok=True);sources=[]
 for sid in ['shot1','shot3']:
  if case=='study2':
   src=OLD/'inputs'/f'{sid}.json'; x=read(src);sources.append(src)
  else:
   src=EEC/'experiments/study01_gs_v12_20260915'/case
   m=src/'entities/manifest.json'; e=src/'entities/shots'/sid/'entities.json'; c=src/'geometry/calibration'/f'{sid}.json'
   es=read(e); fs=next(s['frames'] for s in read(m)['shots'] if s['shot_id']==sid)
   x=dict(shot_id=sid,frames=fs,entities=es['entities'],image_sizes=[list(Image.open(f['path']).size) for f in fs],calibration=read(c));sources.extend([m,e,c])
  assert [f['frame_id'] for f in x['frames']]==[r['frame_id'] for r in x['calibration']['records']]
  for f in x['frames']:assert sha(f['path'])==f['sha256']
  save(out/'inputs'/f'{sid}.json',x)
 shutil.copy2(OLD/'yyfz233--Pi3X_download.json',out/'yyfz233--Pi3X_download.json')
 save(out/'reuse.json',dict(stages=['WeDetect-Anything detection','isolated Codex clustering','own-shot GeoCalib gravity'],new_tokens=0,new_model_inference_seconds=0,sources=[dict(path=str(p),sha256=sha(p)) for p in sources]))
 save(out/'run.json',dict(status='prepared',prepared_at=time.time()))
 print(case,[(s,len(read(out/'inputs'/f'{s}.json')['entities']),read(out/'inputs'/f'{s}.json')['image_sizes'][0]) for s in ['shot1','shot3']])
src=(OLD/'run_depth_boxer.py').read_text();src=src[:src.index(' # Hold the original')]+" save(out/'inference_complete.json',{'status':'complete','seconds':time.time()-start,'allocation':allocation})\nif __name__=='__main__':main()\n"
src=src.replace('HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]',"BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])")
(HERE/'boxer.py').write_text(src)
src=(OLD/'run_geometry.py').read_text().replace('HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]',"BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])")
(HERE/'geometry.py').write_text(src)
shutil.copy2(EEC/'prompts/shot_motion_isolated_v0.2.txt',HERE/'prompts/shot_motion_isolated_v0.2.txt')
shutil.copy2(EEC/'experiments/study2_keypoint_proposal_review_20260916/prompts/gs_relation_shot_v1.txt',HERE/'prompts/gs_relation_shot_v1.txt')
