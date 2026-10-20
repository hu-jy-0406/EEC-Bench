"""Frozen-input identity ablations. No geometry fitting or downstream model replay."""
import copy,hashlib,json,os,sys,time,traceback,argparse
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parent; B=ROOT.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_efficient_transport as transport
from gs_flow1_compact_payload import pack,dump
from review_aligned_entity_identities import validate,FOCUSED_SCHEMA,FOCUSED_PROTOCOL
from gs_entity_appearance_compact import cost
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(Path(p).read_text())
def save(p,x):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
BASES=read(B/'experiments/gravity_free_pipeline_20260921/baselines.json')
VARIANTS=['full','no_native','no_frame3d','no_projection','no_plot','lean','visual','visual_no_boxes','lean_no_story','lean_no_prior']

def reduced(canonical,images,variant):
 if variant=='lean_center_min':
  p,ims=reduced(canonical,images,'lean_centers')
  p.pop('all_initial_paired_group_diagnostics',None)
  for shot in p['shots']:
   for entity in shot['entities']:entity.pop('aggregation',None)
  return p,ims
 if variant=='lean_geometry_no_prior':
  p,ims=reduced(canonical,images,'lean_geometry_only')
  for g in p['initial_matching']['groups']:
   for k in ['identity_evidence','anchor_reason']:g[k]=''
  for k in ['scene_correspondence','limitations','reference_selection_reason']:p['initial_matching'][k]=''
  return p,ims
 p=copy.deepcopy(canonical);images=copy.deepcopy(images)
 lean=variant.startswith('lean');visual=variant.startswith('visual')
 if variant=='no_native':
  for s in p['shots']:
   s.pop('own_scene_cameras',None)
   for e in s['entities']:
    e.pop('own_scene_geometry',None)
    for f in e['frame_evidence']:f.pop('geometry',None)
 if variant=='no_frame3d':
  for s in p['shots']:
   for e in s['entities']:e.pop('frame_evidence',None)
 if variant=='no_projection':
  for s in p['shots']:
   for e in s['entities']:e.pop('projected_center_in_other_shot',None)
 if lean or visual:
  for s in p['shots']:
   s.pop('own_scene_cameras',None)
   for e in s['entities']:
    e.pop('own_scene_geometry',None);e.pop('frame_evidence',None);e.pop('projected_center_in_other_shot',None)
    e['observations']=[{k:f[k] for k in ['frame_id','exist','visible','box_xyxy'] if k in f} for f in e['observations']]
    # Preserve input collection scope via original matching group records, no entity merges.
    for k in ['motion_evidence','motion_status_role','motion_classification_protocol']:e.pop(k,None)
    if e['aligned_geometry']:
     e['aligned_geometry']={k:e['aligned_geometry'][k] for k in ['center_world','size_xyz']}
    e['aggregation']={k:e['aggregation'][k] for k in ['status','center_mad_xyz','size_mad_xyz','selected_frame_ids','rejected_frame_ids','confidence_is_calibrated'] if k in e['aggregation']}
    if visual:
     e.pop('aligned_geometry');e.pop('aggregation')
    if variant=='visual_no_boxes':e.pop('observations')
  p.pop('frozen_transform',None)
  if visual:
   for k in ['all_initial_paired_group_diagnostics','registration_quality','registration_objective']:p.pop(k,None)
 if variant in ['lean_pair_summary','lean_no_uncertainty']:
  for s in p['shots']:
   for e in s['entities']:
    e.pop('aligned_geometry' if variant=='lean_pair_summary' else 'aggregation',None)
 if variant=='lean_no_pairdiag':p.pop('all_initial_paired_group_diagnostics',None)
 if variant in ['lean_geometry_only','lean_uncertainty_only','lean_distance_only']:
  keep={'lean_geometry_only':'aligned_geometry','lean_uncertainty_only':'aggregation','lean_distance_only':None}[variant]
  for s in p['shots']:
   for e in s['entities']:
    for k in ['aligned_geometry','aggregation']:
     if k!=keep:e.pop(k,None)
  if variant!='lean_distance_only':p.pop('all_initial_paired_group_diagnostics',None)
 if variant in ['lean_centers','lean_trajectories']:
  original={e['entity_id']:e for s in canonical['shots'] for e in s['entities']}
  for s in p['shots']:
   for e in s['entities']:
    rows=[]
    for f in original[e['entity_id']]['frame_evidence']:
     geom=f.get('aligned_geometry');row=dict(frame_id=f['frame_id'],visible=f.get('visible'),aligned_center=None if geom is None else geom['center_world'])
     if variant=='lean_trajectories':row['object_axis_side_lengths']=None if geom is None else geom['size_xyz']
     rows.append(row)
    e['aligned_trajectory']=rows
 if variant=='lean_no_story':p['normal_story_prompt']={'facts':[],'note':'Story evidence intentionally withheld in this input ablation; no action may be inferred from omission.'}
 if variant=='lean_no_prior':
  for g in p['initial_matching']['groups']:
   for k in ['identity_evidence','anchor_reason']:g[k]=''
  for k in ['scene_correspondence','limitations','reference_selection_reason']:p['initial_matching'][k]=''
 if variant=='no_plot' or lean or visual:
  p.pop('diagnostic_attachment',None);images=[im for im in images if im['shot_id']!='aligned_diagnostic']
 return p,images

def signature(m):
 def group(g):return (tuple(sorted(g['a_ids'])),tuple(sorted(g['b_ids'])),g['identity'])
 gs={g['group_id']:g for g in m['groups']}
 return {'population':sorted(group(g) for g in m['groups']),
  'confirmed_links':sorted((g['a_ids'][0],g['b_ids'][0]) for g in m['groups'] if g['identity']=='matched'),
  'anchor_eligible':sorted(group(g) for g in m['groups'] if g['anchor_eligible']),
  'anchors':sorted(group(gs[k]) for k in m['structural_anchor_group_ids']),
  'references':[group(gs[m[k]]) if m[k] else None for k in ['local_origin_group_id','local_reference_group_id']]}

def differences(a,b):
 sa,sb=signature(a),signature(b)
 return {k:{'equal':sa[k]==sb[k],'old':sa[k],'new':sb[k]} for k in sa}

def prepare(study,variant,repeat):
 case=Path(BASES[study])/'pairs/pair_000';out=ROOT/'runs'/study/variant/f'r{repeat}'
 canonical=read(case/'identity_review_payload.json');images=read(case/'identity_review_images.json')
 p,ims=reduced(canonical,images,variant)
 out.mkdir(parents=True,exist_ok=True)
 if not (out/'canonical_input.json').exists():save(out/'canonical_input.json',canonical)
 save(out/'ablation_input.json',p);save(out/'images.json',ims)
 source={str(case/n):sha(case/n) for n in ['identity_review_payload.json','identity_review_images.json','matching.json','matching_initial.json','registration/roma_geometry/registration.json']}
 for im in ims:assert sha(im['path'])==im['sha256']
 assert [e['entity_id'] for s in p['shots'] for e in s['entities']]==[e['entity_id'] for s in canonical['shots'] for e in s['entities']]
 assert [(x['shot_id'],x['frame_id'],x['sha256']) for x in ims if x['shot_id']!='aligned_diagnostic']==[(x['shot_id'],x['frame_id'],x['sha256']) for x in images if x['shot_id']!='aligned_diagnostic']
 meta=dict(study=study,variant=variant,repeat=repeat,source_case=str(case),source_hashes=source,
  image_count=len(ims),wire_characters=len(dump(pack(p))),input_characters=len(dump(p)),model='gpt-6-astra',reasoning='medium',protocol=FOCUSED_PROTOCOL)
 save(out/'manifest.json',meta)
 return out,canonical,p,ims,meta

def run(study,variant,repeat):
 start=time.time();out,canonical,p,images,meta=prepare(study,variant,repeat)
 final=out/'result.json'
 if final.exists():return read(final)
 args=SimpleNamespace(out=out/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 prompt=ROOT/'prompt.txt'
 try:
  response=transport.call('identity_review',prompt,p,images,FOCUSED_SCHEMA,args)
  validate(response,canonical,FOCUSED_PROTOCOL)
  old=read(Path(meta['source_case'])/'matching.json');diff=differences(old,response['matching'])
  for path,h in meta['source_hashes'].items():assert sha(path)==h
  state=dict(status='success',**meta,seconds=time.time()-start,differences=diff,
    exact_population=diff['population']['equal'],exact_links=diff['confirmed_links']['equal'],exact_anchors=diff['anchors']['equal'] and diff['references']['equal'],
    actions=[{k:r[k] for k in ['initial_group_id','action','result_group_ids','visual_identity_evidence']} for r in response['initial_group_reviews'] if r['action']!='keep'])
 except Exception as exc:state=dict(status='failed',**meta,seconds=time.time()-start,error=repr(exc),traceback=traceback.format_exc())
 status=args.out/'identity_review/status.json'
 if status.exists():
  s=read(status);usage=s.get('usage',s.get('known_usage',[]));state.update(call_seconds=s['seconds'],usage=usage,total_tokens=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in usage),standard_api_equivalent_usd=cost(usage))
 save(final,state);print(json.dumps({k:state.get(k) for k in ['study','variant','repeat','status','exact_population','exact_links','exact_anchors','call_seconds','total_tokens','standard_api_equivalent_usd','error']}),flush=True)
 return state

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--workers',type=int,default=2);a=parser.parse_args();owned_compute_job()
 jobs=read(ROOT/a.plan);state=dict(status='running',pid=os.getpid(),started=time.time(),allocation=os.environ['SLURM_JOB_ID'],jobs=jobs,results=[]);status=ROOT/(Path(a.plan).stem+'_status.json');save(status,state)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:
  fs=[pool.submit(run,**j) for j in jobs]
  for f in as_completed(fs):state['results'].append(f.result());save(status,state)
 state.update(status='complete',seconds=time.time()-state['started']);save(status,state)
if __name__=='__main__':main()
