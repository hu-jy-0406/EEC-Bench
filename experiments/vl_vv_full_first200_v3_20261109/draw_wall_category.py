#!/usr/bin/env python3
"""Figures of the wall/floor category: confirmed V-V issues of the first run (old) whose subject was an agent-added
wall/floor/ground entity (n..., counted as unspecified, no box), which this rerun (new) reports on the contract
place (pb..., specified). Per case: the old issue's cited frames (max 4), the new subject's ledger box (the place),
and the contract's place description. Input: wall_issue_audit.json. Output: wall_category/*.png."""
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXP = Path(__file__).resolve().parent
OUT = EXP / 'wall_category'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
TILE_W = 330
COLS = 4
GREEN = '#2ca02c'

# (task, old unit, old wall subject labels in English, new unit(s), new place subject)
CASES = [
    ('priority_003__wan21', 'V3', 'n1 kitchen wall covering', 'V2+V9, V9', 'pb0003'),
    ('priority_023__wan22', 'V3', 'n1 washroom walls and tiles', 'V4', 'pb0003'),
    ('priority_047__wan21', 'V4', 'n1 training-room wall structure', 'V3+V7', 'pb0005'),
    ('priority_059__wan21', 'V2', 'n1 red wall, n2 central door, n3 grey floor', 'V7', 'pb0007'),
    ('priority_088__wan21', 'V2', 'n2 living-room wall, n3 living-room window', 'V2+V11', 'pb0004'),
    ('priority_115__wan21', 'V4', 'n1 smooth teal wall (Shot4)', 'V6', 'pb0004'),
    ('priority_118__wan21', 'V1', 'n1 bright brick wall (Shot4)', 'V5', 'pb0004'),
    ('priority_065__wan21', 'V2', 'n1 stone wall', 'V1, V8', 'pb0006'),
    ('priority_012__storymem', 'V1', 'n1 grid screens and wall structure', 'V5+V10', 'pb0004'),
    ('priority_067__wan22', 'V1.1', 'n1 restaurant wall and window structures', 'V8', 'pb0010'),
    ('priority_128__wan21', 'V6', 'n1 pink ground, n2 soil clods (+ pb0009, pb0010)', 'V7, V12', 'pb0006'),
    ('priority_007__wan22', 'V4', 'n1 booth seats, window frames and wall layout', 'V11', 'pb0004'),
]


def read(p):
    return json.loads(Path(p).read_text())


def main():
    OUT.mkdir(exist_ok=True)
    font, small, big = ImageFont.truetype(FONT, 15), ImageFont.truetype(FONT, 13), ImageFont.truetype(BOLD, 17)
    audit = {(a['task'], a['old_unit']): a for a in read(EXP / 'wall_issue_audit.json')}
    st = {}
    for path in (EXP / 'runs').glob('*/progress.json'):
        for tid, s in read(path)['tasks'].items():
            if s.get('status') == 'success' and s.get('mode') == 'reuse_vv':
                st[tid] = s
    blocks = []
    for i, (tid, old_unit, old_label, new_units, place) in enumerate(CASES, 1):
        a = audit[(tid, old_unit)]
        case = Path(st[tid]['case_dir'])
        frames = {(s['shot_id'], f['frame_id']): f['path'] for s in read(case / 'raw_manifest.json')['shots'] for f in s['frames']}
        led = read(case / 'episode_entities.json')
        ent = next(e for e in led['prompt_bound'] if e['global_entity_id'] == place)
        boxes = {}
        for occ in ent.get('occurrences') or []:
            for b in occ.get('boxes') or []:
                boxes.setdefault((occ['shot_id'], b['frame_id']), []).append(b['box_xyxy'])
        model, prio = tid.split('__')[1], tid.split('_')[1]
        lines = [(f'{i}. {model} #{prio}', big),
                 (f'OLD {old_unit}: subject {old_label}  ->  agent-added, counted UNSPECIFIED, no box', None),
                 (f'NEW {new_units}: subject {place} "{ent["name"]}" (contract place, SPECIFIED), green box = its ledger box', None)]
        for part in textwrap.wrap(f'Contract place description: "{ent.get("description", "")}"', 150):
            lines.append((part, small))
        head = Image.new('RGB', (TILE_W * COLS, 10 + 22 * len(lines)), '#f2f2f2')
        d = ImageDraw.Draw(head)
        for k, (text, f) in enumerate(lines):
            d.text((8, 5 + 22 * k), text, fill='black', font=f or font)
        tiles = []
        for shot, frame in [tuple(x) for x in a['old_frames']][:COLS]:
            img = Image.open(frames[(shot, frame)]).convert('RGB')
            scale = TILE_W / img.width
            img = img.resize((TILE_W, round(img.height * scale)))
            dd = ImageDraw.Draw(img)
            dd.rectangle([0, 0, 120, 20], fill='black')
            dd.text((5, 3), f'{shot} frame {frame}', fill='white', font=small)
            for box in boxes.get((shot, frame), []):
                x0, y0, x1, y1 = [v * scale for v in box]
                dd.rectangle([x0 + 1, max(y0, 21) + 1, x1 - 2, y1 - 2], outline=GREEN, width=3)
                dd.rectangle([x1 - 60, y1 - 20, x1 - 2, y1 - 2], fill=GREEN)
                dd.text((x1 - 56, y1 - 18), place, fill='white', font=small)
            tiles.append(img)
        strip = Image.new('RGB', (TILE_W * COLS, max(t.height for t in tiles)), 'white')
        for k, t in enumerate(tiles):
            strip.paste(t, (k * TILE_W, 0))
        blocks.append((head, strip))
    for page, chunk in enumerate((blocks[:6], blocks[6:]), 1):
        h = sum(a.height + b.height + 14 for a, b in chunk)
        canvas = Image.new('RGB', (TILE_W * COLS, h), 'white')
        y = 0
        for head, strip in chunk:
            canvas.paste(head, (0, y)); y += head.height
            canvas.paste(strip, (0, y)); y += strip.height + 14
        path = OUT / f'wall_category_{page}.png'
        canvas.save(path)
        print(path, canvas.size)


if __name__ == '__main__':
    main()
