"""One fresh call per historical identity protocol, sharing frozen baseline geometry."""
import os,sys,json,copy,time,hashlib,socket,traceback,shutil
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
os.environ.setdefault('MPLCONFIGDIR','/tmp/eec_identity_replay_mpl')
H=Path(__file__).resolve().parent; B=H.parents[1]
OLD=B/'experiments/study2_full_fresh_20260918/study2'
NEW=B/'experiments/study2_anchor_joint_fresh_20260918/study2'
sys.path.insert(0,str(B/'scripts'));sys.path.insert(0,str(NEW.parent))
import numpy as np
import run_partial_scene_comparison as transport
import review_aligned_entity_identities as old_contract
import anchor_joint_contract as new_contract
from run_isolated_shot_static_3d import owned_compute_job
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
 job=owned_compute_job();start=time.time()
 assert not (H/'calls').exists(), 'Fresh requests only; do not silently reuse/repeat calls'
 manifest={}
 def source(p):manifest[str(p)]=sha(p);return read(p)
 old=source(OLD/'calls/identity_review/input.json')
 template=source(NEW/'calls/joint_identity_presence/input.json')
 old_images=source(OLD/'identity_review_images.json')
 new=dict(stage=template['stage'])
 for k in ['shots','frozen_transform','registration_quality','normal_story_prompt','images']:
  new[k]=copy.deepcopy(old[k])
 for k in ['registration_anchors','aligned_frame','diagnostic_attachment']:
  new[k]=copy.deepcopy(template[k])
 aux=[]
 for shot in ['shot1','shot3']:
  graph=source(OLD/'selected'/f'{shot}_scene.json');inp=source(OLD/'inputs'/f'{shot}.json')
  obs={shot+'/'+e['entity_id']:e['observations'] for e in inp['entities']}
  aux.append(dict(shot_id=shot,entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],observations=obs[e['entity_id']]) for e in graph['entities']]))
 new['auxiliary_full_motion_inventories']=aux
 source(OLD/'registration/roma_geometry/registration.json')
 for im in old_images:
  p=Path(im['path']);assert sha(p)==im['sha256'];manifest[str(p)]=im['sha256']
 # Original prompt bytes and output schemas retained for both methods.
 prompts=H/'prompts';prompts.mkdir(exist_ok=True)
 for stage,src in [('original',OLD/'calls/identity_review'),('joint',NEW/'calls/joint_identity_presence')]:
  pp=src/'prompt.txt';manifest[str(pp)]=sha(pp)
  intro=pp.read_text().split('\nINPUT_JSON:\n',1)[0]
  (prompts/f'{stage}.txt').write_text(intro)
 original_schema=source(OLD/'calls/identity_review/output.schema.json')
 joint_schema=source(NEW/'calls/joint_identity_presence/output.schema.json')
 assert original_schema==old_contract.SCHEMA and joint_schema==new_contract.JOINT
 assert (prompts/'original.txt').read_text()+'\nINPUT_JSON:\n'+json.dumps(old,ensure_ascii=False)==(OLD/'calls/identity_review/prompt.txt').read_text()
 # Recreate the newer protocol's neutral XY diagram using the SAME baseline boxes.
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.lines import Line2D
 fig,ax=plt.subplots(figsize=(11,8));colors=['#1769ba','#df6b17'];lookup={e['entity_id']:e for s in new['shots'] for e in s['entities']}
 edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
 for side,s in enumerate(new['shots']):
  for e in s['entities']:
   b=e['aligned_geometry'];c=np.array(b['corners_world']);v=np.array(b['center_world']);ax.scatter(*v[:2],s=14,c=colors[side]);ax.annotate(e['entity_id'],v[:2],xytext=(3,4 if side==0 else -10),textcoords='offset points',fontsize=6,color=colors[side])
   for i,j in edges:ax.plot(*c[[i,j],:2].T,color=colors[side],lw=.5,alpha=.3)
 for a in new['registration_anchors']['anchors']:
  xy=np.array([lookup[a[k]]['aligned_geometry']['center_world'][:2] for k in ['a_id','b_id']]);ax.plot(*xy.T,':',c='gray',lw=.7)
 ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_xlabel('X: fixed Shot1 scene');ax.set_ylabel('Y: fixed Shot1 scene');ax.set_title('All static entities / proposed scene alignment\nDotted links: registration anchors only; all other identities unassigned');ax.legend(handles=[Line2D([0],[0],color=c,label=s) for c,s in zip(colors,['Shot1','Shot3'])]);fig.tight_layout()
 plot=H/'joint_alignment_frozen.png';fig.savefig(plot,dpi=130);plt.close(fig)
 new_images=copy.deepcopy(old_images[:12])+[dict(path=str(plot),sha256=sha(plot),shot_id='aligned_diagnostic',frame_id=-1)]
 assert old['shots']==new['shots'] and old['frozen_transform']==new['frozen_transform']
 assert old['registration_quality']==new['registration_quality']
 assert old_images[:12]==new_images[:12]
 # Reuse the old request's disabled-skills setting, not its session/context.
 req=source(OLD/'calls/identity_review/request.json');disabled=next(x for x in req['command'] if x.startswith('skills.config='))
 args=SimpleNamespace(out=H/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=disabled)
 transport.PROMPTS=prompts
 save(H/'frozen_manifest.json',dict(sources=manifest,baseline=str(OLD),allocation=job,host=socket.gethostname(),same_shots=True,same_original_images=True,same_transform=True,same_registration_quality=True,same_story=True,old_prompt_byte_identical=True,protocol_differences=['full initial matching vs structural anchors only','per-pair numeric diagnostics vs individual coordinates','all prior pair links vs anchor-only plot links','per-group identity audit vs joint identity/presence task'],inference_calls_planned=2,no_registration_refit=True))
 for stage,payload,images in [('original',old,old_images),('joint',new,new_images)]:
  save(H/'prepared'/f'{stage}_input.json',payload);save(H/'prepared'/f'{stage}_images.json',images)
 def work(stage,payload,images,schema):
  print('START',stage,time.time(),flush=True)
  result=transport.call(stage,f'{stage}.txt',payload,images,schema,args)
  try:
   if stage=='original':old_contract.validate(result,payload)
   else:save(H/'joint_normalized_presence.json',new_contract.validate_joint(result,payload))
   save(H/f'{stage}_validation.json',dict(passed=True))
  except Exception as exc:
   save(H/f'{stage}_validation.json',dict(passed=False,error=repr(exc),traceback=traceback.format_exc()));raise
  print('DONE',stage,time.time(),flush=True);return stage
 errors=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  jobs=[pool.submit(work,'original',old,old_images,original_schema),pool.submit(work,'joint',new,new_images,joint_schema)]
  for f in jobs:
   try:f.result()
   except Exception as exc:errors.append(repr(exc));traceback.print_exc()
 unchanged=all(sha(Path(p))==v for p,v in manifest.items())
 save(H/'run.json',dict(started=start,ended=time.time(),wall_seconds=time.time()-start,errors=errors,sources_unchanged=unchanged,model=args.model,reasoning=args.reasoning))
 assert unchanged
 if errors:raise RuntimeError(str(errors))
 print('ALL COMPLETE',flush=True)
if __name__=='__main__':main()
