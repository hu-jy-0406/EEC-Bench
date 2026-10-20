#!/usr/bin/env python3
"""Validate completed detector runs; build per-frame tables and HTML gallery."""
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
from PIL import Image, ImageDraw

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runs', nargs='+', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
runs=[json.loads((r/'run.json').read_text()) for r in a.runs]
assert all(r['status']=='success' for r in runs)
expected=[(f['shot'],f['frame_id'],f['sha256']) for f in runs[0]['frames']]
assert all([(f['shot'],f['frame_id'],f['sha256']) for f in r['frames']]==expected for r in runs)
summary={}
md=['# YOLOE / Florence-2 关键帧检测结果','',
    '逐帧对象检测，类别来自模型；没有人工真值，因此数量不是准确率，也不是跨帧去重后的实体数。',
    'YOLOE 默认报告阈值 0.25；Florence-2 OD 不提供可直接比较的检测置信度。','',
    '| 模型 | Shot | 帧 ID | 检测数 | 原始类别（帧内数量） |',
    '|---|---|---:|---:|---|']
page=['<!doctype html><meta charset="utf-8"><title>Keyframe detector comparison</title>',
      '<style>body{font:16px sans-serif;margin:24px;background:#fafafa} .row{display:flex;gap:12px} .cell{flex:1;min-width:0} img{width:100%} pre{white-space:pre-wrap} summary{cursor:pointer} h2{margin-top:40px}</style>',
      '<h1>YOLOE / Florence-2: identical frozen keyframes</h1><p>Frame-local detections, not unique tracks or accuracy. Click an image for full resolution.</p>']
all_data={}
for root,run in zip(a.runs,runs):
    per_shot=defaultdict(list)
    model=run['model']
    assert len(run['results'])==len(expected)
    assert [(x['shot'],x['frame_id']) for x in run['results']]==[(x[0],x[1]) for x in expected]
    for fr in run['frames']:
        directory=root/fr['shot']/f"frame_{fr['frame_id']:06d}"
        d=json.loads((directory/'detections.json').read_text())
        assert d['sha256']==fr['sha256']
        assert hashlib.sha256(Path(fr['path']).read_bytes()).hexdigest()==fr['sha256']
        w,h=d['image_size']
        for det in d['detections']:
            x1,y1,x2,y2=det['box_xyxy']
            assert 0<=x1<x2<=w and 0<=y1<y2<=h, det
            assert det['label']
            if 'mask' in det:
                mask=Image.open(directory/det['mask'])
                assert mask.size==(w,h) and mask.getbbox() is not None
        if model=='florence':
            g=json.loads((directory/'generation.json').read_text())
            assert not g['potentially_truncated'], g
        assert (directory/'boxes.jpg').is_file()
        all_data[(model,fr['shot'],fr['frame_id'])]=(d,directory)
        per_shot[fr['shot']].append(d)
        c=Counter(x['label'] for x in d['detections'])
        labels=', '.join(f'{k} ×{v}' if v>1 else k for k,v in sorted(c.items()))
        md.append(f"| {model} | {fr['shot']} | {fr['frame_id']} | {len(d['detections'])} | {labels} |")
    summary[model]={}
    for shot,rows in per_shot.items():
        names=Counter(x['label'] for row in rows for x in row['detections'])
        freq=Counter(name for row in rows for name in set(x['label'] for x in row['detections']))
        summary[model][shot]=dict(frame_counts=[len(r['detections']) for r in rows],
                    total_detections=sum(names.values()), unique_label_count=len(names),
                    label_occurrences=dict(sorted(names.items())), label_frame_frequency=dict(sorted(freq.items())))
        sheet=Image.new('RGB',(854*2,510*3),'white')
        draw=ImageDraw.Draw(sheet)
        for i,row in enumerate(rows):
            im=Image.open(root/shot/f"frame_{row['frame_id']:06d}"/'boxes.jpg')
            im.thumbnail((854,480))
            x,y=(i%2)*854,(i//2)*510
            sheet.paste(im,(x,y+30))
            draw.text((x+8,y+8),f"{model} | {shot} | frame {row['frame_id']} | n={len(row['detections'])}",fill='black')
        sheet.save(a.output/f'{model}_{shot}.jpg',quality=95)
for shot,fid,_ in expected:
    page.append(f'<h2>{html.escape(shot)} — frame {fid}</h2><div class="row">')
    for model in summary:
        d,directory=all_data[(model,shot,fid)]
        import os
        rel=os.path.relpath(directory/'boxes.jpg',a.output)
        page.append(f'<div class="cell"><h3>{model}: {len(d["detections"])} detections</h3><a href="{rel}"><img src="{rel}"></a><details><summary>Labels / boxes / scores</summary><pre>{html.escape(json.dumps(d["detections"],ensure_ascii=False,indent=2))}</pre></details></div>')
    page.append('</div>')
(a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(a.output/'results.md').write_text('\n'.join(md)+'\n')
(a.output/'index.html').write_text('\n'.join(page))
(a.output/'validation.json').write_text(json.dumps(dict(status='pass',runs=[str(x.resolve()) for x in a.runs],
    frames_per_model=len(expected), checked=['completed runs','exact shared input hashes','all frames once','box bounds','nonempty labels','mask dimensions and nonempty masks','Florence generation not truncated','visualization files']),indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
