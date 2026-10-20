"""Check native row objects with shared witness records, before a full call."""
import copy
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'scripts'))
import gs_gemini_backend as backend

schema = json.loads((ROOT / 'call/gemini_output.schema.json').read_text())
row = schema['properties']['initial_group_reviews']['properties']['g01']
witness = copy.deepcopy(row['properties']['witnesses']['items'])
for row in schema['properties']['initial_group_reviews']['properties'].values():
    row['properties']['witnesses'] = {'type':'array', 'items':{'type':'integer'}}
schema['properties']['identity_review_witnesses'] = {'type':'array', 'items':witness}
schema['required'].append('identity_review_witnesses')
backend.save(ROOT / 'pool_schema.json', schema)
body, _ = backend.build_request('Schema acceptance check. Empty arrays and explanations, uncertain actions.', schema, [], 'minimal')
body['max_tokens'] = 16
try:
    result = backend.send(body, 120)
except Exception as exc:
    result = {'error': str(exc)}
backend.save(ROOT / 'pool_probe.json', result)
print(json.dumps({k:v for k,v in result.items() if k in ['error','usage','model']}))
