#!/usr/bin/env python3
"""Keyframes with the ledger boxes of chosen entities: specified (pb) in blue, unspecified (ge) in orange."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
case, out = Path(sys.argv[1]), Path(sys.argv[2])
cells = [tuple(x.split(':')) for x in sys.argv[3].split(',')]          # Shot5:2,...
keys = set(sys.argv[4].split(','))
m = json.loads((case / 'raw_manifest.json').read_text())
paths = {(s['shot_id'], f['frame_id']): f['path'] for s in m['shots'] for f in s['frames']}
led = json.loads((case / 'episode_entities.json').read_text())
boxes = {}
for kind in ('prompt_bound', 'prompt_unbound'):
    for e in led[kind]:
        if e['global_entity_id'] in keys:
            for o in e.get('occurrences') or []:
                for b in o.get('boxes') or []:
                    boxes.setdefault((o['shot_id'], b['frame_id']), []).append((e['global_entity_id'], b['box_xyxy']))
W = 560
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
tiles = []
for shot, fr in cells:
    fr = int(fr)
    im = Image.open(paths[(shot, fr)]).convert('RGB'); sc = W / im.width
    im = im.resize((W, round(im.height * sc))); d = ImageDraw.Draw(im)
    for key, (x0, y0, x1, y1) in boxes.get((shot, fr), []):
        col = '#1f6fd1' if key.startswith('pb') else '#e07b00'
        d.rectangle([x0 * sc, y0 * sc, x1 * sc, y1 * sc], outline=col, width=3)
        ty = max(y0 * sc - 18, 24)
        d.rectangle([x0 * sc, ty, x0 * sc + 8 * len(key) + 6, ty + 17], fill=col); d.text((x0 * sc + 3, ty + 1), key, fill='white', font=font)
    d.rectangle([0, 0, 150, 22], fill='black'); d.text((5, 3), f'{shot} frame {fr}', fill='white', font=font)
    tiles.append(im)
sheet = Image.new('RGB', (W * len(tiles), max(t.height for t in tiles) + 26), 'white')
for i, t in enumerate(tiles): sheet.paste(t, (i * W, 0))
d = ImageDraw.Draw(sheet)
d.text((8, sheet.height - 22), 'blue = specified (contract entity, pb...)    orange = unspecified (ledger ge...)', fill='black', font=font)
sheet.save(out); print(out, sheet.size)
