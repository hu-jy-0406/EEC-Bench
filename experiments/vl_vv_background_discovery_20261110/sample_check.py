#!/usr/bin/env python3
"""Random sample (seed 20261110) of 12 discovered objects, excluding the five matched to audit findings: one frame
each (first listed frame with a box, else the first listed frame), all Grounding DINO boxes of that object, the
shot's registered entity names and the object's description, for a visual check. Writes grounding_check/sample_<k>.png."""
import json, random, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
EXCL = {('priority_025__storymem', 'Shot2:b1'), ('priority_036__holocine', 'Shot4:b4'), ('priority_047__storymem', 'Shot2:b3'),
        ('priority_047__storymem', 'Shot5:b3'), ('priority_120__storymem', 'Shot3:b2')}
req = json.loads((HERE / 'grounding_request.json').read_text())
objs = []
for resp in sorted(HERE.glob('runs/*/*/response.json')):
    task, shot = resp.parent.parent.name, resp.parent.name
    reg = [e['name'] for e in json.loads((resp.parent / 'input.json').read_text())['registered']]
    for k, o in enumerate(json.loads(resp.read_text())['objects'], 1):
        if (task, f'{shot}:b{k}') not in EXCL:
            objs.append(dict(task=task, shot=shot, target=f'{shot}:b{k}', reg=reg, **o))
sample = random.Random(20261110).sample(objs, 12)
tiles = []
for o in sample:
    best = None
    for fr in req['frames']:
        if fr['shot_id'] != f"{o['task']}__{o['shot']}" or not any(t['prompt_entity_id'] == o['target'] for t in fr['targets']):
            continue
        res = json.loads((HERE / 'grounding' / fr['shot_id'] / f"frame_{fr['frame_id']:06d}.json").read_text())
        boxes = [d for d in res['detections'] if d['prompt_entity_id'] == o['target'] and d['valid_box']]
        if best is None or (boxes and not best[1]):
            best = (fr, boxes)
        if boxes: break
    fr, boxes = best
    im = Image.open(fr['path']).convert('RGB'); sc = 560 / im.width; im = im.resize((560, round(im.height * sc))); d = ImageDraw.Draw(im)
    for b in boxes:
        x0, y0, x1, y1 = [v * sc for v in b['box_xyxy']]; d.rectangle([x0, y0, x1, y1], outline='#ff2d55', width=3)
        d.text((x0 + 3, y0 + 2), f"{b['score']:.2f}", fill='#ff2d55', font=FONT)
    head = Image.new('RGB', (560, 74), 'white'); hd = ImageDraw.Draw(head)
    lines = [f"{o['task']} {o['shot']} f{fr['frame_id']}  {o['name']} ({o['in_prompt']})"] + textwrap.wrap(o['description'], 88)[:2] + \
            [('registered: ' + ', '.join(o['reg']))[:92]]
    for i, l in enumerate(lines): hd.text((4, 2 + 18 * i), l, fill='black', font=FONT)
    tile = Image.new('RGB', (560, im.height + 74), 'white'); tile.paste(head, (0, 0)); tile.paste(im, (0, 74)); tiles.append(tile)
for s in range(3):
    part = tiles[s * 4:(s + 1) * 4]; h = max(t.height for t in part)
    sheet = Image.new('RGB', (1120, h * 2), 'white')
    for i, t in enumerate(part): sheet.paste(t, ((i % 2) * 560, (i // 2) * h))
    sheet.save(HERE / 'grounding_check' / f'sample_{s + 1}.png')
print([(o['task'], o['target'], o['name']) for o in sample])
