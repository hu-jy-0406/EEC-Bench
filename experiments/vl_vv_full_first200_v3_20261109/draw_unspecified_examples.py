#!/usr/bin/env python3
"""Draw example figures: confirmed V-V issues of the first run (old) that counted as unspecified because the agent
added a background part as a new entity (n...), next to the same videos' issues in this run (new).

Per example one PNG in unspecified_examples/: an OLD row (frames cited by the old issue) and a NEW row (frames cited by
the new issue). Boxes are the unchanged ledger boxes of the subject entities in those frames (the reuse case is the
first run's frontend, so both rows use the same ledger and keyframes). Agent-added entities (n...) have no ledger
record and therefore no box. ASCII labels only (no CJK font on the cluster)."""
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXP = Path(__file__).resolve().parent
OUT = EXP / 'unspecified_examples'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
COLORS = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#00a3a3', '#f032e6', '#9a6324']
TILE_W = 416

EXAMPLES = [
    dict(task='priority_003__wan21', file='1_wan21_003_kitchen_wall.png', title='Wan2.1 #003  kitchen wall',
         old=['V3'], new=['V2+V9', 'V9'], n_names={'n1': 'kitchen wall covering'}),
    dict(task='priority_007__wan21', file='2_wan21_007_diner_window_booth.png',
         title='Wan2.1 #007  diner window framing and booth seats',
         old=['V1.1', 'V1.2'], new=['V5', 'V6'], n_names={'n1': 'diner window framing', 'n2': 'diner booth seating'}),
    dict(task='priority_090__wan21', file='3_wan21_090_pool_tiles.png', title='Wan2.1 #090  pool wall tiles',
         old=['V2'], new=['V3+V4'], n_names={'n1': 'pool wall tile surface'}),
    dict(task='priority_065__wan21', file='4_wan21_065_stone_wall.png', title='Wan2.1 #065  stone wall',
         old=['V2'], new=['V8'], n_names={'n1': 'stone wall'}),
    dict(task='priority_011__wan22', file='5_wan22_011_washroom.png', title='Wan2.2 #011  washroom fixtures',
         old=['V1'], new=[], n_names={'n1': 'teal stalls', 'n2': 'grey frosted door', 'n3': 'high windows',
                                      'n4': 'mosaic wall band', 'n5': 'white louvred wall'}),
    dict(task='priority_086__wan21', file='6_wan21_086_duplicate_man.png',
         title='Wan2.1 #086  duplicated man (a real entity, for contrast)',
         old=['V2'], new=['V3+V5+V12'], n_names={'n1': 'repeated bald bearded man'}),
]


def read(path):
    return json.loads(Path(path).read_text())


def task_state(tid):
    for path in (EXP / 'runs').glob('*/progress.json'):
        state = read(path)['tasks'].get(tid)
        if state and state.get('status') == 'success':
            return state
    raise KeyError(tid)


def frames_of(case):
    manifest = read(case / 'raw_manifest.json')
    return {(s['shot_id'], f['frame_id']): f['path'] for s in manifest['shots'] for f in s['frames']}


def ledger(case):
    led = read(case / 'episode_entities.json')
    out = {}
    for kind in ('prompt_bound', 'prompt_unbound'):
        for e in led[kind]:
            boxes = {}
            for occ in e.get('occurrences') or []:
                for b in occ.get('boxes') or []:
                    boxes.setdefault((occ['shot_id'], b['frame_id']), []).append(b['box_xyxy'])
            out[e['global_entity_id']] = dict(name=e.get('name') or '', boxes=boxes)
    return out


def units(results, ids):
    by_id = {u['unit_id']: u for u in read(results / 'vv_review/result.json')['units']}
    return [by_id[i] for i in ids]


def label_of(key, led, n_names):
    if key in led:
        return f'{key} "{led[key]["name"]}"'
    return f'{key} "{n_names.get(key, "?")}" (agent-added, no ledger box)'


def draw_row(units_, frames, led, n_names, colors, font, small):
    cells, seen = [], []
    for u in units_:
        subjects = [r['entity_key'] for r in u.get('entity_refs') or [] if r.get('role') == 'subject']
        for ref in u['frame_refs']:
            key = (ref['shot_id'], ref['frame_id'])
            if key not in seen:
                seen.append(key)
                cells.append([key, set()])
            next(c for c in cells if c[0] == key)[1].update(subjects)
    tiles = []
    for (shot, frame), subjects in cells:
        img = Image.open(frames[(shot, frame)]).convert('RGB')
        scale = TILE_W / img.width
        img = img.resize((TILE_W, round(img.height * scale)))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 150, 24], fill='black')
        d.text((6, 3), f'{shot} frame {frame}', fill='white', font=small)
        for key in sorted(subjects):
            for box in (led.get(key) or {}).get('boxes', {}).get((shot, frame), []):
                x0, y0, x1, y1 = [v * scale for v in box]
                d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], outline=colors[key], width=4)
                tw = d.textlength(key, font=small)
                ty = y0 - 20 if y0 >= 46 else max(y0 + 2, 26)
                d.rectangle([x0 + 1, ty, x0 + tw + 9, ty + 19], fill=colors[key])
                d.text((x0 + 5, ty + 1), key, fill='white', font=small)
        tiles.append(img)
    return tiles


def header(lines, width, font, fill):
    wrapped = []
    for line, bold in lines:
        for part in textwrap.wrap(line, width=max(40, width // 10)) or ['']:
            wrapped.append((part, bold))
    h = 12 + 24 * len(wrapped)
    img = Image.new('RGB', (width, h), fill)
    d = ImageDraw.Draw(img)
    y = 6
    for text, bold in wrapped:
        d.text((10, y), text, fill='black', font=bold or font)
        y += 24
    return img


def main():
    OUT.mkdir(exist_ok=True)
    font, small = ImageFont.truetype(FONT, 17), ImageFont.truetype(FONT, 14)
    big = ImageFont.truetype(BOLD, 22)
    index = []
    for ex in EXAMPLES:
        st = task_state(ex['task'])
        case = Path(st['case_dir'])
        frames, led = frames_of(case), ledger(case)
        old_units = units(Path(st['source_attempt']) / 'results', ex['old'])
        new_units = units(Path(st['output_dir']), ex['new']) if ex['new'] else []
        keys = []
        for u in old_units + new_units:
            for r in u.get('entity_refs') or []:
                if r.get('role') == 'subject' and r['entity_key'] not in keys:
                    keys.append(r['entity_key'])
        colors = {k: COLORS[i % len(COLORS)] for i, k in enumerate(keys)}
        rows = []
        for side, us in (('OLD (first run)', old_units), ('NEW (this rerun)', new_units)):
            if not us:
                rows.append(([(f'{side}: no confirmed issue of this kind in this video', big)], []))
                continue
            lines = [(side, big)]
            for u in us:
                subs = [r['entity_key'] for r in u.get('entity_refs') or [] if r.get('role') == 'subject']
                lab = '; '.join(label_of(k, led, ex['n_names']) for k in subs)
                lines.append((f'{u["unit_id"]} {u["scope"]} {u["subcategory"]} | subject: {lab}', None))
            rows.append((lines, draw_row(us, frames, led, ex['n_names'], colors, font, small)))
        width = TILE_W * 3
        parts = [header([(ex['title'], big)], width, font, '#dddddd')]
        for lines, tiles in rows:
            parts.append(header(lines, width, font, '#f4f4f4'))
            for start in range(0, len(tiles), 3):
                chunk = tiles[start:start + 3]
                strip = Image.new('RGB', (width, max(t.height for t in chunk)), 'white')
                for i, t in enumerate(chunk):
                    strip.paste(t, (i * TILE_W, 0))
                parts.append(strip)
        canvas = Image.new('RGB', (width, sum(p.height for p in parts) + 4 * len(parts)), 'white')
        y = 0
        for p in parts:
            canvas.paste(p, (0, y))
            y += p.height + 4
        canvas.save(OUT / ex['file'])
        index.append(dict(file=ex['file'], task=ex['task'], old=ex['old'], new=ex['new']))
        print(OUT / ex['file'], canvas.size)
    (OUT / 'index.json').write_text(json.dumps(index, indent=1) + '\n')


if __name__ == '__main__':
    main()
