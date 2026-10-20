from pathlib import Path
import json,hashlib,ast,sys
H=Path(__file__).resolve().parent;B=H.parents[1];spec=json.loads((H/'spec.json').read_text());OLD=Path(spec['baseline'])
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(root):
 rows=[]
 for sid in ['shot1','shot3']:
  p=root/'shots'/sid;s=read(p/'status.json');u=s['usage'];rows.append(dict(shot=sid,input_tokens=sum(x['input_tokens'] for x in u),output_tokens=sum(x['output_tokens'] for x in u),cached_input_tokens=sum(x.get('cached_input_tokens',0) for x in u),seconds=s['finished']-s['started'],prompt_bytes=(p/'prompt.txt').stat().st_size))
 for r in rows:r['total_tokens']=r['input_tokens']+r['output_tokens']
 r=read(root/'run.json');return dict(shots=rows,total_tokens=sum(x['total_tokens'] for x in rows),input_tokens=sum(x['input_tokens'] for x in rows),output_tokens=sum(x['output_tokens'] for x in rows),seconds=r['review_finished']-r['review_started'])
baseline=stats(OLD);runs=[]
for arg in sys.argv[1:]:
 root=H/arg;r=read(root/'run.json');assert r['status']=='success' and r['detector_mode']=='reuse';check=[]
 for sid in ['shot1','shot3']:
  op=OLD/'shots'/sid;np=root/'shots'/sid;old=read(op/'entities.json');new=read(np/'entities.json');assert read(op/'input.json')==read(np/'input.json')
  os={frozenset(e['candidate_ids']):e for e in old['entities']};ns={frozenset(e['candidate_ids']):e for e in new['entities']}
  orej={r['candidate_id'] for r in old['rejected_detections']};nrej={r['candidate_id'] for r in new['rejected_detections']}
  changed=[];names=[]
  for k in os.keys() & ns.keys():
   a,b=os[k],ns[k];names.append(dict(old=a['name'],new=b['name']))
   if a['observations']!=b['observations']:changed.append(dict(old=a['entity_id'],new=b['entity_id']))
  req=read(np/'request.json');cmd=req['command'];assert '--ephemeral' in cmd and '--ignore-user-config' in cmd
  assert cmd[cmd.index('--model')+1]=='gpt-6-astra' and 'model_reasoning_effort="medium"' in cmd
  check.append(dict(shot=sid,old_entities=len(os),new_entities=len(ns),clusters_equal=set(os)==set(ns),rejected_candidates_equal=orej==nrej,all_derived_observations_equal=not changed,old_only=[dict(name=os[k]['name'],ids=sorted(k)) for k in os.keys()-ns.keys()],new_only=[dict(name=ns[k]['name'],ids=sorted(k)) for k in ns.keys()-os.keys()],rejection_change=dict(newly_rejected=sorted(nrej-orej),newly_retained=sorted(orej-nrej)),names=names))
 val=dict(run=arg,stats=stats(root),quality=check);val['structural_quality_gate_passed']=all(x['clusters_equal'] and x['rejected_candidates_equal'] and x['all_derived_observations_equal'] for x in check);val['reduction_fraction']=1-val['stats']['total_tokens']/baseline['total_tokens'];runs.append(val)
 print(json.dumps({**val,'quality':[{k:v for k,v in x.items() if k!='names'} for x in check]},ensure_ascii=False,indent=2))
# Detector code was not modified during prompt/transport optimization.
old_source=(H/'baseline_source/scripts/run_wedetect_shot_entities.py').read_text();new_source=(B/'scripts/run_wedetect_shot_entities.py').read_text()
def functions(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
a,b=functions(old_source),functions(new_source);same={n:a[n]==b[n] for n in ['detect','load_detections','make_payload','check_gpu']};assert all(same.values())
result=dict(baseline=baseline,runs=runs,detector_functions_unchanged=same,limitations='Fixed Study2 Shot1/Shot3 replay tests observed equivalence, not universal accuracy or stability guarantee. No detector inference was repeated because detector code/settings/data were held fixed.')
(H/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
