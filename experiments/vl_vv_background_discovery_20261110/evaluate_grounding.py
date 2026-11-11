#!/usr/bin/env python3
"""Grounding DINO results for the discovered objects: per object, in how many of its listed frames at least one
valid box came back (box 0.30 / text 0.25, unchanged script). Draws the boxes of chosen targets for checking.
Writes grounding_summary.json and grounding_check/<task>_<shot>_<target>.png."""
import json, sys, collections
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
req = json.loads((HERE / 'grounding_request.json').read_text())
hits = collections.defaultdict(dict)   # (task, shot, target) -> frame -> [boxes]
paths = {}
for fr in req['frames']:
    task, shot = fr['shot_id'].rsplit('__', 1)
    paths[(task, shot, fr['frame_id'])] = fr['path']
    res = json.loads((HERE / 'grounding' / fr['shot_id'] / f"frame_{fr['frame_id']:06d}.json").read_text())
    for t in fr['targets']:
        hits[(task, shot, t['prompt_entity_id'])].setdefault(fr['frame_id'], [])
    for d in res['detections']:
        if d['valid_box']:
            hits[(task, shot, d['prompt_entity_id'])][fr['frame_id']].append(dict(box=d['box_xyxy'], score=round(d['score'], 3), phrase=d['name']))
names = {}
for resp in HERE.glob('runs/*/*/response.json'):
    task, shot = resp.parent.parent.name, resp.parent.name
    for k, o in enumerate(json.loads(resp.read_text())['objects'], 1):
        names[(task, shot, f'{shot}:b{k}')] = o['name']
cls = collections.Counter(); rows = []
for key, frames in hits.items():
    n = len(frames); m = sum(1 for v in frames.values() if v)
    c = 'all' if m == n else 'some' if m else 'none'; cls[c] += 1
    rows.append(dict(task=key[0], shot=key[1], target=key[2], name=names.get(key), frames=n, frames_with_box=m,
                     boxes_per_frame=round(sum(len(v) for v in frames.values()) / n, 2)))
summary = dict(objects=len(rows), boxed_in_all_frames=cls['all'], boxed_in_some=cls['some'], boxed_in_none=cls['none'],
               mean_boxes_per_listed_frame=round(sum(r['boxes_per_frame'] for r in rows) / len(rows), 2))
(HERE / 'grounding_summary.json').write_text(json.dumps(dict(summary=summary, objects=rows), indent=1, ensure_ascii=False) + '\n')
print(json.dumps(summary, indent=1))
(HERE / 'grounding_check').mkdir(exist_ok=True)
for spec in sys.argv[1:]:                       # task:shot:bk
    task, shot, b = spec.split(':'); key = (task, shot, f'{shot}:{b}')
    tiles = []
    for fr in sorted(hits[key])[:3]:
        im = Image.open(paths[(task, shot, fr)]).convert('RGB'); sc = 560 / im.width
        im = im.resize((560, round(im.height * sc))); d = ImageDraw.Draw(im)
        for h in hits[key][fr]:
            x0, y0, x1, y1 = [v * sc for v in h['box']]
            d.rectangle([x0, y0, x1, y1], outline='#ff2d55', width=3)
            d.rectangle([x0, max(y0 - 17, 0), x0 + 52, max(y0 - 17, 0) + 17], fill='#ff2d55'); d.text((x0 + 3, max(y0 - 17, 0)), f"{h['score']:.2f}", fill='white', font=FONT)
        d.rectangle([0, im.height - 19, 92, im.height], fill='black'); d.text((3, im.height - 18), f'{shot} f{fr}', fill='white', font=FONT)
        tiles.append(im)
    sheet = Image.new('RGB', (560 * max(1, len(tiles)), (max(t.height for t in tiles) if tiles else 40) + 22), 'white')
    ImageDraw.Draw(sheet).text((5, 3), f"{task} {shot} {b}: {names.get(key)}  (Grounding DINO boxes, query from discovery)", fill='black', font=FONT)
    for i, t in enumerate(tiles): sheet.paste(t, (i * 560, 22))
    sheet.save(HERE / 'grounding_check' / f'{task}_{shot}_{b}.png')
    print(spec, names.get(key), {fr: len(v) for fr, v in hits[key].items()})
