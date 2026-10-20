"""Small read-only progress/cost view; model-stage totals, not actual billing."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent
summary={}
for mode in ['boundary_compact_medium','shots_compact_medium']:
 for n in ['study2','study3','study4']:
  p=R/mode/n;rows=[]
  for f in p.glob('calls/*/status.json'):
   d=json.loads(f.read_text());usage=d.get('usage',d.get('known_usage',[]));usage=[usage] if isinstance(usage,dict) else usage
   cost=0;tokens=0
   for u in usage:
    a=u.get('input_tokens',0);c=u.get('cached_input_tokens',0);w=u.get('cache_write_input_tokens',0);o=u.get('output_tokens',0);large=a>272000
    cost+=((a-c-w)*10+c+w*12.5)*(2 if large else 1)/1e6+o*50*(1.5 if large else 1)/1e6;tokens+=a+o
   rows.append(dict(call=f.parent.name,status=d['status'],seconds=d.get('seconds'),tokens=tokens,usd=round(cost,6)))
  summary[mode+'/'+n]=rows
print(json.dumps(summary,indent=2))
