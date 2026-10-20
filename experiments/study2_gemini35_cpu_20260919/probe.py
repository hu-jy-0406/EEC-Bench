import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parents[1] / 'scripts'))
from gs_gemini_backend import build_request, send, save
manifest = json.loads((root / 'manifest.json').read_text())
frame = manifest['shots'][0]['frames'][0]['path']
schema = dict(type='object', properties={'ok': {'type': 'boolean'}}, required=['ok'], additionalProperties=False)
body, records = build_request('Return {"ok":true} if you received an image.', schema, [frame])
body['max_tokens'] = 1024
raw = send(body, 60)
save(root / 'api_probe.json', dict(response=raw, attachments=records, reasoning='medium'))
assert raw['choices'][0]['finish_reason'] == 'stop'
assert json.loads(raw['choices'][0]['message']['content']) == {'ok': True}
print(json.dumps(dict(model=raw['model'], usage=raw['usage'], status='multimodal_schema_medium_passed')))
