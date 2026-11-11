#!/usr/bin/env python3
"""Contact sheet of chosen keyframes of one case (rows = shots, columns = frame ids), ASCII labels."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
case, out, shots, frames = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].split(','), [int(x) for x in sys.argv[4].split(',')]
m = json.loads((case / 'raw_manifest.json').read_text())
paths = {(s['shot_id'], f['frame_id']): f['path'] for s in m['shots'] for f in s['frames']}
W = 420
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 15)
tiles = []
for s in shots:
    row = []
    for f in frames:
        im = Image.open(paths[(s, f)]).convert('RGB')
        im = im.resize((W, round(im.height * W / im.width)))
        d = ImageDraw.Draw(im); d.rectangle([0, 0, 135, 22], fill='black'); d.text((5, 3), f'{s} frame {f}', fill='white', font=font)
        row.append(im)
    tiles.append(row)
h = tiles[0][0].height
sheet = Image.new('RGB', (W * len(frames), h * len(shots)), 'white')
for i, row in enumerate(tiles):
    for j, im in enumerate(row):
        sheet.paste(im, (j * W, i * h))
sheet.save(out); print(out, sheet.size)
