"""Check required native JSON objects with a shared application row schema."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
import gs_gemini_backend as backend
schema=json.loads((ROOT/'call/gemini_output.schema.json').read_text())
for gid in schema['properties']['initial_group_reviews']['properties']:
    schema['properties']['initial_group_reviews']['properties'][gid]={'type':'object','additionalProperties':True}
backend.save(ROOT/'open_rows_schema.json',schema)
body,_=backend.build_request('Schema acceptance check. Empty arrays and explanations, uncertain actions.',schema,[],'minimal')
body['max_tokens']=16
try: result=backend.send(body,120)
except Exception as exc: result={'error':str(exc)}
backend.save(ROOT/'open_rows_probe.json',result)
print(json.dumps({k:v for k,v in result.items() if k in ['error','usage','model']}))
