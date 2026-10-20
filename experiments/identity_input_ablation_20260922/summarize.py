import csv,json
from pathlib import Path
R=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
rows=[]
for p in sorted((R/'runs').glob('*/*/*/result.json')):
 d=read(p);u=d.get('usage',[])
 row={k:d.get(k) for k in ['study','variant','repeat','status','exact_population','exact_links','exact_anchors','image_count','wire_characters','call_seconds','total_tokens','standard_api_equivalent_usd']}
 row['input_tokens']=sum(x.get('input_tokens',0) for x in u);row['cached_input_tokens']=sum(x.get('cached_input_tokens',0) for x in u);row['output_tokens']=sum(x.get('output_tokens',0) for x in u)
 row['usd_without_cache']=(row['input_tokens']*10+row['output_tokens']*50)/1e6
 row['result_path']=str(p);rows.append(row)
 if d.get('status')=='success':
  for k,v in d['differences'].items():
   if not v['equal']:print(d['study'],d['variant'],d['repeat'],'DIFF',k,'old-only',[x for x in v['old'] if x not in v['new']],'new-only',[x for x in v['new'] if x not in v['old']])
print('\nSUMMARY')
for r in rows:print(r['study'],r['variant'],r['repeat'],r['status'],r['exact_population'],r['exact_links'],r['exact_anchors'],round(r['call_seconds'] or 0,1),r['total_tokens'],round(r['standard_api_equivalent_usd'] or 0,4))
if rows:
 with (R/'calls.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 totals=dict(calls=len(rows),tokens=sum(r['total_tokens'] or 0 for r in rows),standard_api_equivalent_usd=sum(r['standard_api_equivalent_usd'] or 0 for r in rows),summed_call_seconds=sum(r['call_seconds'] or 0 for r in rows),not_a_bill=True,pricing='Recorded Astra standard USD/M input10 cached1 output50; actual calls below272k input. Cache is a subset of input.')
 (R/'usage_summary.json').write_text(json.dumps(totals,indent=2)+'\n');print('TOTAL',totals)
