"""Frozen response/input equivalence replay. No model or GPU calls."""
import copy,json,sys,shutil,time,threading
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
S=ROOT.parents[1]/'scripts';sys.path.insert(0,str(S))
import run_gs_temporal_stage as stage
import gs_entity_appearance_compact as compact
import gs_entity_appearance_minimal as minimal
import gs_entity_appearance_scoring as scoring
OLD=ROOT.parent/'study3_appearance_full_20260921/run'
read=lambda p:json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def boundary():
 src=OLD/'pairs/pair_000';out=ROOT/'frozen_boundary_v2';out.mkdir()
 for name in ['inputs','selected','registration']:
  shutil.copytree(src/name,out/name)
 for name in ['matching.json','narrative.json']:
  shutil.copy2(src/name,out/name)
 obj=stage.Stage.__new__(stage.Stage);obj.case=out;obj.story=read(out/'narrative.json')
 obj.runtime=read(OLD/'runtime_profile.json');obj.scheduling={'parallel_boundary':True}
 seen=[];lock=threading.Lock();running=set();peak=[0]
 def call(name,prompt,payload,images,schema):
  before=src/'calls'/name
  full=dict(payload,images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=f['image_size']) for i,f in enumerate(images)])
  assert full==read(before/'input.json'),name+' input changed'
  assert schema==read(before/'output.schema.json'),name+' schema changed'
  promptpath=Path(prompt)
  if promptpath.is_absolute():assert promptpath.read_text()==(src/'boundary/restored_prompts'/promptpath.name).read_text()
  with lock:seen.append(name);running.add(name);peak[0]=max(peak[0],len(running))
  time.sleep(.1 if name=='boundary_review_000' else .025)
  with lock:running.remove(name)
  return read(before/'response.json')
 obj.call=call
 obj.boundary()
 assert read(out/'boundary/results.json')==read(src/'boundary/results.json')
 assert len(seen)==4 and len(set(seen))==4 and peak[0]>=3,(seen,peak)
 return dict(exact_inputs_schemas_results=True,calls=len(seen),peak_parallel_calls=peak[0])

def appearance():
 out=ROOT/'frozen_appearance_v2';compact.prepare(OLD/'appearance/canonical',out,defer_dino=True)
 m=read(out/'manifest.json');m['source_hashes'].update({str(Path(minimal.__file__).resolve()):compact.sha(minimal.__file__),str(minimal.BASE):compact.sha(minimal.BASE)});save(out/'manifest.json',m)
 old=OLD/'appearance/compact'
 for e in m['entities']:
  eid=e['global_entity_id'];f=out/'entities'/eid;b=old/'entities'/eid
  assert not (f/'dino.json').exists()
  assert read(f/'wire.json')==read(b/'wire.json')
  assert [i['sha256'] for i in read(f/'images.json')]==[i['sha256'] for i in read(b/'images.json')]
  shutil.copy2(b/'codex.json',f/'codex.json')
  if (old/'calls'/eid).exists():
   dest=out/'calls'/eid;dest.mkdir(parents=True)
   for name in ['response.json','status.json','output.schema.json','prompt.txt','execution_override.json']:
    shutil.copy2(old/'calls'/eid/name,dest/name)
 report=ROOT/'frozen_appearance_report_v2';scoring.report([out],report)
 a=read(report/'results.json')['studies'][0];b=read(OLD/'appearance/report/results.json')['studies'][0]
 for k in ['all_entities','multi_shot_entities','single_shot_entities','entities']:
  assert ([{kk:vv for kk,vv in row.items() if kk!='study'} for row in a[k]]==[{kk:vv for kk,vv in row.items() if kk!='study'} for row in b[k]]) if k=='entities' else a[k]==b[k],k
 return dict(exact_wire_inputs_sheets_scores=True,entities=len(m['entities']),audit=read(report/'audit.json'))

if __name__=='__main__':
 result=dict(boundary=boundary(),appearance=appearance(),new_model_calls=0,new_tokens=0,new_api_usd=0)
 save(ROOT/'frozen_validation.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
