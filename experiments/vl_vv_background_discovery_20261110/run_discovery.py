#!/usr/bin/env python3
"""Background-object discovery test (owner, 2026-11-10: "按照你说的顺序验证"), step 1a: one isolated model call per shot
of the 20 audited videos (../vl_vv_full_first200_v3_20261109/miss_diagnosis/audit20/index.json). Input: that shot's
labelled keyframes, its own prompt text, and its own final local entity list (shot_prompt_recovery/entities). Output:
objects visible but not registered (prompt_discovery_v0.txt). GPT-6 Luna, reasoning low, API transport (run under
scripts/openai_api_env.sh). Calls are saved under runs/<task>/<shot>/; no pipeline file is changed."""
import json, sys, hashlib, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
B = HERE.parents[1]
sys.path.insert(0, str(B / 'scripts'))
import gs_prompt_binding as gpb
V3 = B / 'experiments/vl_vv_full_first200_v3_20261109'
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["objects"], "properties": {"objects": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["name", "query", "description", "location", "frames", "in_prompt"],
    "properties": {"name": {"type": "string"}, "query": {"type": "string"}, "description": {"type": "string"}, "location": {"type": "string"},
                   "frames": {"type": "array", "items": {"type": "integer"}}, "in_prompt": {"type": "string", "enum": ["yes", "no", "unsure"]}}}}}}
LOCK = threading.Lock()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tasks():
    states = {}
    for path in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in json.loads(path.read_text())['tasks'].items():
            if t.get('status') == 'success': states[tid] = t
    jobs = []
    for row in json.loads((V3 / 'miss_diagnosis/audit20/index.json').read_text()):
        case = Path(states[row['task']]['case_dir'])
        manifest = json.loads((case / 'raw_manifest.json').read_text())
        prompt = {s['shot_id']: s['text'] for s in json.loads((case / 'prompt.json').read_text())['shots']}
        for s in manifest['shots']:
            ents = json.loads((case / f"shot_prompt_recovery/entities/shots/{s['shot_id']}/entities.json").read_text())['entities']
            jobs.append(dict(task=row['task'], shot=s['shot_id'], text=prompt[s['shot_id']],
                             registered=[dict(id=e['entity_id'], name=e.get('name')) for e in ents],
                             images=[dict(path=f['path'], sha256=sha(f['path']), shot_id=s['shot_id'], frame_id=f['frame_id']) for f in s['frames']]))
    return jobs


def one(job):
    folder = HERE / 'runs' / job['task'] / job['shot']
    if (folder / 'status.json').exists() and json.loads((folder / 'status.json').read_text()).get('status') == 'success':
        return job['task'], job['shot'], 'skipped', None
    payload = dict(shot_id=job['shot'], shot_text=job['text'], registered=job['registered'],
                   frames=[i['frame_id'] for i in job['images']])
    try:
        out = gpb.call(folder, payload, job['images'], 600, prompt_path=HERE / 'prompt_discovery_v0.txt', schema=SCHEMA,
                       model='gpt-6-luna', reasoning='low')
        return job['task'], job['shot'], 'success', len(out['objects'])
    except Exception as e:
        return job['task'], job['shot'], 'failed', repr(e)[:200]


if __name__ == '__main__':
    jobs = tasks()
    print('shots', len(jobs), flush=True)
    with ThreadPoolExecutor(8) as pool:
        for r in pool.map(one, jobs):
            print(*r, flush=True)
