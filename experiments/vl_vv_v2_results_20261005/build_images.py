#!/usr/bin/env python3
"""Build page images from original keyframes: one contact sheet per case and one strip per reference artifact."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'page/img'
RUNS = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
        ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
try:
    FONT = ImageFont.truetype('/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', 15)
except OSError:
    FONT = ImageFont.load_default()


def frames_dir():
    rows = {}
    for path in RUNS:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows[(row['generation_priority'], row['model_id'])] = Path(row['output_dir']).parent / 'work/frames'
    return rows


def label(img, text):
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), text, font=FONT)
    d.rectangle((0, 0, box[2] + 10, box[3] + 8), fill=(0, 0, 0))
    d.text((5, 3), text, fill=(255, 255, 255), font=FONT)


def frame(root, shot, fid):
    return Image.open(root / shot / f'frame_{fid:06d}.jpg').convert('RGB')


def main():
    ref = json.loads((HERE / 'results_reference.json').read_text())
    dirs = frames_dir()
    for case in ref['cases']:
        root = dirs[(case['priority'], case['model'])]
        shots = sorted([p.name for p in root.iterdir() if p.is_dir()], key=lambda s: int(s[4:]))
        w, h = 216, 125
        sheet = Image.new('RGB', (w * 6 + 7 * 2, (h + 2) * len(shots) + 2), (20, 20, 20))
        for r, shot in enumerate(shots):
            for c in range(6):
                im = frame(root, shot, c).resize((w, h), Image.LANCZOS)
                if c == 0:
                    label(im, shot.replace('Shot', 'S'))
                sheet.paste(im, (2 + c * (w + 2), 2 + r * (h + 2)))
        sheet.save(OUT / f'{case["key"]}_sheet.jpg', quality=82, optimize=True)
        for art in case['artifacts']:
            tiles = []
            for shot, fid in art['evidence']:
                im = frame(root, shot, fid).resize((384, 222), Image.LANCZOS)
                label(im, f'{shot} · f{fid}')
                tiles.append(im)
            strip = Image.new('RGB', (len(tiles) * 386 + 2, 226), (20, 20, 20))
            for i, im in enumerate(tiles):
                strip.paste(im, (2 + i * 386, 2))
            strip.save(OUT / f'{case["key"]}_{art["id"]}.jpg', quality=84, optimize=True)
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(len(list(OUT.iterdir())), 'images', round(total / 1e6, 2), 'MB')


if __name__ == '__main__':
    main()
