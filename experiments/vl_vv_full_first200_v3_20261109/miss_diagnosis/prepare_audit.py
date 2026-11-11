#!/usr/bin/env python3
"""Audit packets for the missed-issue audit (owner, 2026-11-09: "Yes, audit 20").
20 videos of the first-200 rerun, 4 per model, random with a fixed seed. Per video in audit20/<task>/:
sheet_<k>.png (rows = shots, columns = the 6 keyframes; at most 4 shots per sheet), frames.json (keyframe paths for
zooming), prompt.txt (global and per-shot prompt text), entities.txt (contract entities = what the prompt specifies,
with the shots whose presence lists them), pipeline.json (ledger and V-V results; opened only after the blind pass)."""
import json, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
EXP = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'audit20'
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
TW = 300
tasks = {}
for path in sorted((EXP / 'runs').glob('*/progress.json')):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') == 'success':
            tasks[tid] = t
rng = random.Random(20261109)
chosen = []
for model in ('cinetrans', 'holocine', 'storymem', 'wan21', 'wan22'):
    chosen += rng.sample(sorted(t for t in tasks if t.endswith('__' + model)), 4)
index = []
for tid in chosen:
    t = tasks[tid]; case, res = Path(t['case_dir']), Path(t['output_dir'])
    d = OUT / tid; d.mkdir(parents=True, exist_ok=True)
    m = json.loads((case / 'raw_manifest.json').read_text())
    shots = [s for s in m['shots']]
    frames = {s['shot_id']: [f['path'] for f in s['frames']] for s in shots}
    (d / 'frames.json').write_text(json.dumps(frames, indent=1) + '\n')
    sheets = []
    for k in range(0, len(shots), 4):
        rows = []
        for s in shots[k:k + 4]:
            row = []
            for f in s['frames']:
                im = Image.open(f['path']).convert('RGB'); im = im.resize((TW, round(im.height * TW / im.width)))
                dr = ImageDraw.Draw(im); dr.rectangle([0, 0, 112, 19], fill='black'); dr.text((4, 2), f"{s['shot_id']} f{f['frame_id']}", fill='white', font=FONT)
                row.append(im)
            rows.append(row)
        h = max(im.height for r in rows for im in r)
        sheet = Image.new('RGB', (TW * max(len(r) for r in rows), h * len(rows)), 'white')
        for i, r in enumerate(rows):
            for j, im in enumerate(r):
                sheet.paste(im, (j * TW, i * h))
        name = f'sheet_{k // 4 + 1}.png'; sheet.save(d / name); sheets.append(name)
    p = json.loads((case / 'prompt.json').read_text())
    (d / 'prompt.txt').write_text('GLOBAL: ' + p.get('global_prompt', '') + '\n\n' + '\n\n'.join(f"{s['shot_id']}: {s['text']}" for s in p['shots']) + '\n')
    c = json.loads((case / 'contract.json').read_text())
    shots_of = {}
    for s in c['shots']:
        for i in s['presence']:
            shots_of.setdefault(str(i), []).append(s['shot_id'])
    (d / 'entities.txt').write_text('Contract entities (what the prompt specifies):\n' + '\n'.join(
        f"- [{k}] {v['label']}: {v['name']} - {v['description']} (expected in: {', '.join(shots_of.get(k, [])) or 'none listed'})"
        for k, v in c['entity_descriptions'].items()) + '\n')
    led = json.loads((case / 'episode_entities.json').read_text())
    ledger = [dict(id=e['global_entity_id'], label='specified' if kind == 'prompt_bound' else 'unspecified', name=e.get('name'),
                   shots=sorted({o['shot_id'] for o in e.get('occurrences') or []}))
              for kind in ('prompt_bound', 'prompt_unbound') for e in led[kind]]
    det = json.loads((res / 'vv_detection/result.json').read_text())
    cands = [dict(id=i['issue_id'], scope=i.get('scope'), subcategory=i.get('subcategory'),
                  subjects=[r['entity_key'] for r in i.get('entity_refs') or [] if r.get('role') == 'subject'],
                  description=i['description']) for i in det['issues']]
    added = (det.get('model_output') or {}).get('added_entities') or []
    sc = json.loads((res / 'episode_scoring/result.json').read_text())
    lab = {u['unit_id']: [(s['entity_key'], s['label']) for s in u.get('subject_entities') or []] for u in sc['unit_scores']}
    rv = json.loads((res / 'vv_review/result.json').read_text())
    units = [dict(id=u['unit_id'], from_candidates=u.get('source_candidate_ids'), verdict=u['verdict'], scope=u.get('scope'),
                  subcategory=u['subcategory'], subjects_with_labels=lab.get(u['unit_id']),
                  frames=[(f['shot_id'], f['frame_id']) for f in u.get('frame_refs') or []], description=u['description'])
             for u in rv['units']]
    (d / 'pipeline.json').write_text(json.dumps(dict(task=tid, ledger=ledger, vv_added_entities=added, vv_candidates=cands,
                                                     vv_review_units=units), indent=1, ensure_ascii=False) + '\n')
    index.append(dict(task=tid, shots=len(shots), sheets=sheets, dir=str(d)))
    print(tid, len(shots), 'shots', sheets)
(OUT / 'index.json').write_text(json.dumps(index, indent=1) + '\n')
