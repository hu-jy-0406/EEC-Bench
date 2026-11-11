#!/usr/bin/env python3
"""Low-threshold WeDetect test on the frames of the audit objects missing from the ledger (owner: "Yes, test it").
Production (wedetect_adapter.Detector.predict): proposals objectness > 0.1, NMS 0.7, top 100, then class match >= 0.4.
Here the same model and weights, one forward pass per frame, two proposal sets:
  production-equivalent (0.1, top 100) and extended (objectness > 0.05, top 300); every proposal keeps its best class
  and match score. Image colors: green = production output (match >= 0.4); orange = match 0.30-0.40; magenta = 0.20-0.30;
  thin light blue, unlabeled = proposed (objectness > 0.1) but match < 0.20. Writes wedetect_lowthr/<finding>.png and
  wedetect_lowthr/frames.json. CPU only."""
import json, re, sys
from pathlib import Path
import numpy as np, torch
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent; EXP = HERE.parent
DET = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study_inconsistent_2/detector_upgrade_20260910')
sys.path.insert(0, str(DET))
from wedetect_adapter import Detector
from infer_anything import letterbox, proposal_nms, rescale, np_sigmoid
torch.set_num_threads(4)
det = Detector(DET / 'weights/wedetect_base_uni.pth', 'cpu')
FONT = ImageFont.truetype(str(DET / 'WeDetect/simsun.ttc'), 14)
summary = json.loads((HERE / 'audit20_summary.json').read_text())
tasks = {}
for path in (EXP / 'runs').glob('*/progress.json'):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') == 'success': tasks[tid] = t


def run(im):
    w, h = im.size
    lb, _, _ = letterbox(np.asarray(im).copy(), (640, 640))
    inp = np.ascontiguousarray((lb / 255.).transpose(2, 0, 1)[None].astype(np.float32))
    with torch.inference_mode():
        scores, boxes, embeds = [x[0].cpu().numpy() for x in det.model(torch.from_numpy(inp))]
    prod, _ = proposal_nms(scores, boxes, .1, .7, 100)
    ext, obj = proposal_nms(scores, boxes, .05, .7, 300)
    prod = set(prod.tolist()); out = []
    for k, o in zip(ext.tolist(), obj.tolist()):
        prob = np_sigmoid((det.text @ embeds[k]) * det.scales[k] + det.biases[k])
        cls = int(np.argmax(prob)); s = float(prob[cls])
        box = rescale((640, 640), boxes[k].copy(), (h, w)).round().tolist()
        out.append(dict(label=det.vocab[cls], score=round(s, 3), objectness=round(float(o), 3), box=box,
                        production=(k in prod and s >= .4)))
    return out


frames_out = {}
for f in summary['primary']:
    if f['ledger_status'] != 'not_recorded':
        continue
    blind = {x['id']: x for x in json.loads((HERE / 'audit20' / f['task'] / 'blind_findings.json').read_text())['primary']}[f['id']]
    case = Path(tasks[f['task']]['case_dir'])
    paths = {(s['shot_id'], x['frame_id']): x['path'] for s in json.loads((case / 'raw_manifest.json').read_text())['shots'] for x in s['frames']}
    frames = []
    for ref in blind.get('frames') or []:
        m = re.match(r'(Shot\d+)\s*f(?:rame)?\s*(\d+)', ref)
        if m and (m.group(1), int(m.group(2))) not in frames: frames.append((m.group(1), int(m.group(2))))
    frames = frames[:3] or [(s, 0) for s in blind.get('shots') or []][:3]
    tiles = []
    for shot, fr in frames:
        im = Image.open(paths[(shot, fr)]).convert('RGB')
        props = run(im)
        frames_out[f"{f['task']}:{shot}:f{fr}"] = props
        W = 620; sc = W / im.width; im = im.resize((W, round(im.height * sc))); d = ImageDraw.Draw(im)
        for p in sorted(props, key=lambda p: p['score']):
            x0, y0, x1, y1 = [v * sc for v in p['box']]
            if p['production']: col = '#1a9e3f'
            elif p['score'] >= .3: col = '#ff8c00'
            elif p['score'] >= .2: col = '#d6249f'
            elif p['objectness'] > .1: d.rectangle([x0, y0, x1, y1], outline='#7fb8ff', width=1); continue
            else: continue
            d.rectangle([x0, y0, x1, y1], outline=col, width=2)
            lab = f"{p['label']} {p['score']:.2f}"
            d.rectangle([x0, max(y0 - 16, 0), x0 + 9 * len(lab) + 4, max(y0 - 16, 0) + 16], fill=col)
            d.text((x0 + 2, max(y0 - 16, 0)), lab, fill='white', font=FONT)
        d.rectangle([0, im.height - 18, 120, im.height], fill='black'); d.text((3, im.height - 17), f'{shot} f{fr}', fill='white', font=FONT)
        tiles.append(im)
        n = lambda c: sum(c(p) for p in props)
        print(f['task'], f['id'], shot, fr, 'production', n(lambda p: p['production']), '0.3-0.4', n(lambda p: not p['production'] and p['score'] >= .3),
              '0.2-0.3', n(lambda p: .2 <= p['score'] < .3), 'proposed<0.2', n(lambda p: p['score'] < .2 and p['objectness'] > .1), flush=True)
    sheet = Image.new('RGB', (620 * len(tiles), max(t.height for t in tiles) + 40), 'white'); dd = ImageDraw.Draw(sheet)
    dd.text((5, 3), f"{f['task']} {f['id']}: {f['entity']}"[:140], fill='black', font=FONT)
    dd.text((5, 21), 'green = production output (>=0.40)  orange = 0.30-0.40  magenta = 0.20-0.30  thin blue = proposed, match <0.20', fill='black', font=FONT)
    for i, t in enumerate(tiles): sheet.paste(t, (i * 620, 40))
    sheet.save(HERE / 'wedetect_lowthr' / f"{f['task']}_{f['id']}.png")
(HERE / 'wedetect_lowthr' / 'frames.json').write_text(json.dumps(frames_out, indent=1, ensure_ascii=False) + '\n')
