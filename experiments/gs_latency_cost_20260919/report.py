"""Measured stage accounting; full latency explicitly reconstructed from frozen GPU timings."""
import json,csv
from pathlib import Path
H=Path(__file__).resolve().parent;C=H.parent/'study2_integrated_full_fresh_20260919/study2'
def read(p):return json.loads(p.read_text())
def usd(u,model):
 rates={'gpt-6-astra':(10,1,50),'gpt-5.6-terra':(2,.2,12),'gpt-5.6-luna':(.2,.02,1.2)};i,c,o=rates[model];n=u['input_tokens'];cached=u.get('cached_input_tokens',0);write=u.get('cache_write_input_tokens',0);return ((n-cached-write)*i+cached*c+write*1.25*i)*(2 if n>272000 else 1)/1e6+u['output_tokens']*o*(1.5 if n>272000 else 1)/1e6

def calls(root):
 rows=[]
 for p in sorted(root.glob('*/status.json')):
  state=read(p)
  if 'usage' not in state:continue
  model=state.get('model','gpt-6-astra');us=state['usage'];rows.append(dict(stage=p.parent.name,model=model,reasoning=state.get('reasoning','medium'),seconds=state.get('seconds'),input_tokens=sum(u['input_tokens'] for u in us),output_tokens=sum(u['output_tokens'] for u in us),usd=sum(usd(u,model) for u in us),status=state['status']))
 return rows

def totals(rows):return {k:sum(r[k] for r in rows) for k in ['input_tokens','output_tokens','usd']}|{'total_tokens':sum(r['input_tokens']+r['output_tokens'] for r in rows),'calls':len(rows)}

base=read(C/'summary.json');stages={s['stage']:s['seconds'] for s in base['stages']};front=[]
for p in sorted((C/'entities/shots').glob('*/status.json')):
 u=read(p)['usage'];front.append(dict(stage='cluster_'+p.parent.name,model='gpt-6-astra',reasoning='medium',seconds=None,input_tokens=sum(x['input_tokens'] for x in u),output_tokens=sum(x['output_tokens'] for x in u),usd=sum(usd(x,'gpt-6-astra') for x in u),status='success'))
s2=read(H/'shot2_clustering/result.json');u=s2['usage'];shot2=dict(stage='cluster_shot2',model=s2['model'],reasoning=s2['reasoning'],seconds=s2['seconds'],input_tokens=sum(x['input_tokens'] for x in u),output_tokens=sum(x['output_tokens'] for x in u),usd=sum(usd(x,s2['model']) for x in u),status='success')
basecalls=calls(C/'calls');result=dict(baseline=dict(seconds=base['elapsed_seconds'],shot13=totals(basecalls+front),all3_requested=totals(basecalls+front+[shot2])),shot2=shot2,experiments={})
for variant in ['astra_low_r1','luna_low_r1','terra_low_r1','terra_medium_identity_r2','astra_low_chain_r2','astra_low_suffix_r3','astra_medium_suffix_r4','safe_spatial_medium']:
 root=H/variant;rows=calls(root/'calls' if (root/'calls').exists() else root);record=dict(totals=totals(rows),calls=rows)
 if (root/'quality.json').exists():record['quality']=read(root/'quality.json')
 if (root/'timing.json').exists():record['timing']=read(root/'timing.json')
 result['experiments'][variant]=record
prefix=sum(stages[k] for k in ['detection_and_clustering','geocalib','prepare_shot_inputs','pi3x_shot1','boxer_shot1','pi3x_shot3','boxer_shot3']);numerical=stages['lift_correspondences']+stages['registration']
result['candidate_estimates']={}
for variant in ['astra_low_suffix_r3','astra_medium_suffix_r4']:
 rec=result['experiments'][variant]
 if 'quality' not in rec:continue
 medium='medium' in variant
 upstream=[r for r in (basecalls if medium else result['experiments']['astra_low_chain_r2']['calls']) if r['stage'] in ['motion_shot1','motion_shot3','matching']]
 if medium:mt=stages['motion_and_fusion'];it=stages['initial_identity']
 else:
  ts={s['stage']:s['seconds'] for s in read(H/'astra_low_chain_r2/timing.json')['stages']};mt=ts['motion_and_fusion'];it=ts['initial_identity']
 suffix=sum(s['seconds'] for s in rec['timing']['stages']);t=prefix+max(mt+it,stages['roma_matches'])+numerical+suffix
 result['candidate_estimates'][variant]=dict(shot13_seconds_estimated=t,shot13_seconds_without_overlap_estimated=prefix+mt+it+stages['roma_matches']+numerical+suffix,actual_downstream_seconds=suffix,shot13=totals(upstream+rec['calls']+front),all3_requested=totals(upstream+rec['calls']+front+[shot2]),scope='Frozen upstream stage replay plus newly generated chained downstream. GPU timings reused from baseline; not a fresh end-to-end wall-clock measurement.')
safe=result['experiments']['safe_spatial_medium']
if 'quality' in safe:
 rows=[r for r in basecalls if not (r['stage'].startswith('observe_') or r['stage']=='verify_relations')]+safe['calls']+front
 spatial_time=safe['timing']['stages'][0]['seconds']
 result['candidate_estimates']['safe_spatial_medium']=dict(shot13_seconds_estimated=base['elapsed_seconds']-stages['roma_matches']-stages['spatial']+spatial_time,shot13=totals(rows),all3_requested=totals(rows+[shot2]),actual_spatial_seconds=spatial_time,scope='Only spatial calls re-run; identity/presence unchanged. Full time reconstructed with scheduler overlap and baseline GPU/other stage timings.')
result['validation_cost_usd']=sum(e['totals']['usd'] for e in result['experiments'].values())+shot2['usd'];result['pricing_sources']=['https://developers.openai.com/api/docs/models/gpt-6-astra','https://developers.openai.com/api/docs/models/gpt-5.6-terra','https://developers.openai.com/api/docs/models/gpt-5.6-luna'];result['pricing_scope']='Standard synchronous API equivalent; excludes GPU, network and platform fees. CLI actual invoice is unavailable. No request in this report crosses 272k input.'
(H/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
rows=[dict(experiment=name,**r) for name,e in result['experiments'].items() for r in e['calls']]
with (H/'calls.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps({k:result[k] for k in ['baseline','candidate_estimates','validation_cost_usd']},indent=2))
