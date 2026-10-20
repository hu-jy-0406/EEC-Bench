"""Check required fixed group-to-row slots with fully typed review rows."""
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
import gs_gemini_backend as backend
schema=json.loads((ROOT/'call/output.schema.json').read_text())
ids=json.loads((ROOT/'call/input.json').read_text())['initial_matching']['groups']
ids=[g['group_id'] for g in ids]
row=copy.deepcopy(schema['properties']['initial_group_reviews']['items'])
del row['properties']['initial_group_id']
row['required'].remove('initial_group_id')
schema['properties']['initial_group_reviews']={'type':'object','properties':{gid:{'type':'integer','enum':[i]} for i,gid in enumerate(ids)},'required':ids,'additionalProperties':False}
schema['properties']['initial_group_review_rows']={'type':'array','items':row,'minItems':len(ids),'maxItems':len(ids)}
schema['required'].append('initial_group_review_rows')
backend.save(ROOT/'indexed_schema.json',schema)
body,_=backend.build_request('Schema acceptance check. Empty arrays and explanations, uncertain actions.',schema,[],'minimal')
body['max_tokens']=16
try: result=backend.send(body,120)
except Exception as exc: result={'error':str(exc)}
backend.save(ROOT/'indexed_probe.json',result)
print(json.dumps({k:v for k,v in result.items() if k in ['error','usage','model']}))
