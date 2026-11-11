#!/usr/bin/env python3
"""Static, offline SVG evidence overlays; original pixels embedded unchanged."""
import argparse
import base64
import html
import json
from pathlib import Path


def render(root):
    def read(p):return json.loads(p.read_text())
    result=read(root/'comparison.json');state=read(root/'run.json')
    graphs=[read(root/'source_snapshot'/('graph_'+s+'.json')) for s in result['source_shots']]
    files={(f['shot_id'],f['frame_id']):f for f in read(root/'manifest.json')['images'] if f['role']=='original'}
    for g in graphs:
        for frame in g['frames']:files[(g['shot_id'],frame['frame_id'])]['image_size']=frame['image_size']
    styles='body{font:15px sans-serif;max-width:1250px;margin:24px auto;padding:0 16px}section{border-top:2px solid #aaa;padding:15px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:15px}svg{width:100%;border:1px solid #ddd;background:#eee}pre{white-space:pre-wrap;overflow-wrap:anywhere}.legend{line-height:1.8}details{margin:12px 0}h3{font-size:17px} @media(max-width:700px){.pair{grid-template-columns:1fr}}'
    chunks=['<!doctype html><meta charset="utf-8"><title>局部顺序证据</title><style>'+styles+'</style>',
        '<h1>局部顺序：原始图像与证据</h1><p class="legend">红色：局部查询主体；蓝色：局部查询客体。实线框为推断的落位中心范围，虚线框为实际可见的诊断部位。橙色箭头表示该 shot 的局部物理轴方向。相机改变时箭头方向可以反转，表中结论已归一。框是模型提出的证据范围，不是实测真值。</p>']
    def svg(f,obs,anchor,view=None):
        uri='data:image/'+('png' if f['path'].endswith('.png') else 'jpeg')+';base64,'+base64.b64encode(Path(f['path']).read_bytes()).decode()
        width,height=f['image_size']
        v=view or [0,0,width,height]
        out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="'+' '.join(str(x) for x in v)+'"><image width="'+str(width)+'" height="'+str(height)+'" href="'+uri+'"/>']
        for who,color in [('subject','#ef2222'),('object','#126aff')]:
            for field,dash in [('part_xyxy','5 3'),('center_bounds_xyxy','')]:
                b=obs[who+'_'+field]
                if b:out.append(f'<rect x="{b[0]}" y="{b[1]}" width="{b[2]-b[0]}" height="{b[3]-b[1]}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
        if view is None:
            a=anchor['negative_endpoint_xy'];b=anchor['positive_endpoint_xy']
            if a and b:
                out.append('<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#ff8500"/></marker></defs>')
                out.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#ff8500" stroke-width="4" marker-end="url(#arrow)"/>')
        return ''.join(out)+'</svg>'
    for item in result['items']:
        q=item['query'];chunks+=['<section><h2>'+html.escape(q['reference']+' · '+item['reason_code'])+'</h2>']
        commonframes=set(o['frame_id'] for o in item['evidence']['a']['raw_review'])&set(o['frame_id'] for o in item['evidence']['b']['raw_review'])
        selected=[min(commonframes),max(commonframes)] if commonframes else []
        for fid in dict.fromkeys(selected):
            chunks.append('<h3>Frame '+str(fid)+'</h3><div class="pair">')
            for side,g in zip(('a','b'),graphs):
                names={e['entity_id']:e['name'] for e in g['entities']};local=q[side]
                obs=next(o for o in item['evidence'][side]['raw_review'] if o['frame_id']==fid)
                anchor=next(a for a in g['anchors'] if a['anchor_id']==local['anchor_id'])
                aobs=next(o for o in anchor['observations'] if o['frame_id']==fid)
                text=g['shot_id']+'：'+names[local['subject_id']]+' → '+names[local['object_id']]
                chunks+=['<div><h3>'+html.escape(text)+'</h3><p>'+html.escape(anchor['axis_description'])+'</p>',
                         '<p>提取 / 复核（归一后）：'+html.escape(str(item['evidence'][side]['extracted_values'])+' / '+str(item['evidence'][side]['reviewed_values']))+'</p>']
                boxes=[obs[k] for k in ('subject_part_xyxy','object_part_xyxy','subject_center_bounds_xyxy','object_center_bounds_xyxy') if obs[k]]
                f=files[(g['shot_id'],fid)]
                if boxes:
                    x=max(0,min(b[0] for b in boxes)-30);y=max(0,min(b[1] for b in boxes)-30)
                    xx=min(f['image_size'][0],max(b[2] for b in boxes)+30);yy=min(f['image_size'][1],max(b[3] for b in boxes)+30)
                    chunks.append(svg(f,obs,aobs,[x,y,xx-x,yy-y]))
                chunks+=['<p>'+html.escape(obs['reason'])+'</p><details><summary>原帧与局部轴</summary>',svg(f,obs,aobs),'</details></div>']
            chunks.append('</div>')
        chunks+=['<details><summary>全部逐帧结构化记录</summary><pre>'+html.escape(json.dumps(item,ensure_ascii=False,indent=2))+'</pre></details></section>']
    (root/'viewer.html').write_text(''.join(chunks))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);render(p.parse_args().run.resolve())
