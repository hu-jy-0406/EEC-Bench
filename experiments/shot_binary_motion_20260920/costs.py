"""Measured call usage; frozen clustering composition is explicitly an estimate."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent;BASE=R.parent/'temporal_v2_study234_revised_20260920'
read=lambda p:json.loads(p.read_text())
KEYS=['input','output','cached','tokens','usd','model_seconds']

def usage(path):
    s=read(path);us=s.get('usage',s.get('known_usage',[]));us=[us] if isinstance(us,dict) else us
    r=dict(input=0,output=0,cached=0,tokens=0,usd=0.,model_seconds=s.get('seconds',0),status=s['status'],path=str(path))
    for u in us:
        i=u['input_tokens'];o=u['output_tokens'];c=u.get('cached_input_tokens',0);w=u.get('cache_write_input_tokens',0);large=i>272000
        r['input']+=i;r['output']+=o;r['cached']+=c;r['tokens']+=i+o
        r['usd']+=((i-c-w)*10+c+w*12.5)*(2 if large else 1)/1e6+o*50*(1.5 if large else 1)/1e6
    return r

def total(rows):return {k:sum(r[k] for r in rows) for k in KEYS}

if __name__=='__main__':
    previous={r['study']:r for r in read(R.parent/'temporal_cost_quality_20260920/cost_quality_summary.json')['production']}
    rows=[]
    for name in ['study2','study3','study4']:
        case=R/name
        selected_pair=R/'production_replay'/name/'pairs/pair_000/calls'
        calls=[usage(p) for p in list((case/'calls').glob('*/status.json'))+
               [p for p in selected_pair.glob('*/status.json') if p.parent.name!='boundary_spatial_verify']+
               list((R/'sign_transport_fix'/name/'pairs/pair_000/calls').glob('*/status.json'))]
        rejected=[usage(p) for p in list((case/'pairs/pair_000/calls').glob('*/status.json'))+[selected_pair/'boundary_spatial_verify/status.json']]
        assert all(c['status']=='success' for c in calls)
        baseline=read(BASE/name/'summary.json')
        clustering=[usage(BASE/name/c['call']/'status.json') for c in baseline['calls'] if c['call'].startswith('entities/')]
        row=dict(study=name,production_replay_calls=len(calls),validation_calls=len(calls+rejected),validation=total(calls+rejected),
                 rejected_adapter_calls=len(rejected),rejected_adapter_usage=total(rejected),
                 production_composition=total(calls+clustering),previous_production=previous[name]['estimated_pipeline'],
                 calls=calls)
        for family in ['expected_motion_','within_','matching','identity_review','boundary_review_','boundary_local_','boundary_spatial_verify']:
            row.setdefault('families',{})[family]=total([c for c in calls if Path(c['path']).parent.name.startswith(family)])
        rows.append(row)
    result=dict(scope='Actual fresh model calls; production adds unchanged frozen clustering usage. No measured fresh frontend/GPU/end-to-end latency.',
                pricing=dict(model='gpt-6-astra',uncached_input_usd_per_M=10,cached_input_usd_per_M=1,output_usd_per_M=50,
                             source='https://developers.openai.com/api/docs/models/gpt-6-astra',actual_billing=False),
                cases=rows,validation=total([r['validation'] for r in rows]),production_composition=total([r['production_composition'] for r in rows]))
    (R/'cost_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))
