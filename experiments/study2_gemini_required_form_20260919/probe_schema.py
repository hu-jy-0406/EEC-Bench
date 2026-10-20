"""Tiny schema-acceptance diagnostic, separate from evaluation usage."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import gs_gemini_backend as backend

root = Path(__file__).resolve().parent
original = json.loads((root / 'call/output.schema.json').read_text())
full = json.loads((root / 'call/gemini_output.schema.json').read_text())
one = copy.deepcopy(full)
one['properties']['initial_group_reviews']['properties'] = {'g01': one['properties']['initial_group_reviews']['properties']['g01']}
one['properties']['initial_group_reviews']['required'] = ['g01']
short = copy.deepcopy(full)
for row in short['properties']['initial_group_reviews']['properties'].values():
    names = {name: 'f'+str(i) for i, name in enumerate(row['properties'])}
    row['properties'] = {names[k]: v for k, v in row['properties'].items()}
    row['required'] = [names[k] for k in row['required']]
simple = copy.deepcopy(full)
simple['properties']['initial_group_reviews']['properties'] = {gid: {'type': 'string'} for gid in full['properties']['initial_group_reviews']['required']}
for name, schema in [('original', original), ('one', one), ('short', short), ('simple', simple)]:
    request, _ = backend.build_request('Schema acceptance check. Return empty strings and arrays where allowed, uncertain actions.', schema, [], 'minimal')
    request['max_tokens'] = 16
    try:
        result = backend.send(request, 120)
    except Exception as exc:
        result = {'error': str(exc)}
    backend.save(root / (name + '_probe.json'), result)
    print(name, json.dumps({k:v for k,v in result.items() if k in ['error', 'usage', 'model']}), flush=True)
