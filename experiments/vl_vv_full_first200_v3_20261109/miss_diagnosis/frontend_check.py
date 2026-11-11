#!/usr/bin/env python3
"""For audit primary findings whose object is not in the ledger: draw every raw WeDetect detection on the cited
frames, colored by what shot clustering did with it (green = kept in an entity, red = rejected by the clustering
agent, grey = not given to clustering / filtered). Label = detector class (Chinese) + score + entity id when kept.
Writes frontend_check/<task>_<id>.png and frontend_check/status.json (per frame: detections and their status)."""
import json, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
EXP = HERE.parent
FONT = ImageFont.truetype('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study_inconsistent_2/detector_upgrade_20260910/WeDetect/simsun.ttc', 15)
COL = dict(kept='#1a9e3f', rejected='#d62728', filtered='#888888')
summary = json.loads((HERE / 'audit20_summary.json').read_text())
tasks = {}
for path in (EXP / 'runs').glob('*/progress.json'):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') == 'success':
            tasks[tid] = t
out_status = {}
for f in summary['primary']:
    if f['ledger_status'] != 'not_recorded':
        continue
    blind = {x['id']: x for x in json.loads((HERE / 'audit20' / f['task'] / 'blind_findings.json').read_text())['primary']}[f['id']]
    case = Path(tasks[f['task']]['case_dir'])
    frames = []
    for ref in blind.get('frames') or []:
        m = re.match(r'(Shot\d+)\s*f(?:rame)?\s*(\d+)', ref)
        if m and (m.group(1), int(m.group(2))) not in frames:
            frames.append((m.group(1), int(m.group(2))))
    if not frames:
        frames = [(s, 0) for s in blind.get('shots') or []]
    frames = frames[:3]
    tiles, recs = [], []
    for shot, fr in frames:
        det = json.loads((case / f'entities/detections/{shot}/frame_{fr:06d}/detections.json').read_text())
        ents = json.loads((case / f'entities/shots/{shot}/entities.json').read_text())
        inp = json.loads((case / f'entities/shots/{shot}/input.json').read_text())
        given = {c['candidate_id'] for fr_ in inp['frames'] for c in fr_['detections']}
        kept = {cid: e['entity_id'] for e in ents['entities'] for cid in e.get('candidate_ids') or []}
        rej = set()
        for r in ents.get('rejected_detections') or []:
            for k in ('candidate_ids', 'candidate_id', 'ids'):
                v = r.get(k)
                if v: rej |= set(v if isinstance(v, list) else [v])
        im = Image.open(det['path'] if Path(det['path']).exists() else json.loads((case / 'raw_manifest.json').read_text()) and None).convert('RGB') if Path(det['path']).exists() else None
        if im is None:
            m = json.loads((case / 'raw_manifest.json').read_text())
            p = {(s['shot_id'], x['frame_id']): x['path'] for s in m['shots'] for x in s['frames']}[(shot, fr)]
            im = Image.open(p).convert('RGB')
        W = 560; sc = W / im.width
        im = im.resize((W, round(im.height * sc))); d = ImageDraw.Draw(im)
        for x in det['detections']:
            cid = f"f{fr}:d{x['id']}"
            st = 'kept' if cid in kept else 'rejected' if (cid in rej or cid in given) else 'filtered'
            x0, y0, x1, y1 = [v * sc for v in x['box_xyxy']]
            d.rectangle([x0, y0, x1, y1], outline=COL[st], width=2)
            lab = f"{x['label']} {x['score']:.2f}" + (f" {kept[cid]}" if st == 'kept' else '')
            d.rectangle([x0, max(y0 - 17, 0), x0 + 15 * len(lab) * 0.62 + 6, max(y0 - 17, 0) + 17], fill=COL[st])
            d.text((x0 + 3, max(y0 - 17, 0)), lab, fill='white', font=FONT)
            recs.append(dict(shot=shot, frame=fr, cid=cid, label=x['label'], score=round(x['score'], 3), box=x['box_xyxy'], status=st, entity=kept.get(cid)))
        d.rectangle([0, im.height - 20, 150, im.height], fill='black'); d.text((4, im.height - 19), f'{shot} f{fr}', fill='white', font=FONT)
        tiles.append(im)
    head = 46
    sheet = Image.new('RGB', (560 * len(tiles), max(t.height for t in tiles) + head), 'white')
    dd = ImageDraw.Draw(sheet)
    dd.text((6, 4), f"{f['task']} {f['id']}: {f['entity']}"[:150], fill='black', font=FONT)
    dd.text((6, 24), 'green = kept in entity   red = rejected by clustering   grey = filtered before clustering', fill='black', font=FONT)
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 560, head))
    name = f"{f['task']}_{f['id']}.png"; sheet.save(HERE / 'frontend_check' / name)
    out_status[f"{f['task']}:{f['id']}"] = dict(entity=f['entity'], what=blind.get('what'), frames=frames, detections=recs, image=name)
    print(name, frames, 'dets', len(recs), {s: sum(r['status'] == s for r in recs) for s in COL})
(HERE / 'frontend_check' / 'status.json').write_text(json.dumps(out_status, indent=1, ensure_ascii=False) + '\n')
