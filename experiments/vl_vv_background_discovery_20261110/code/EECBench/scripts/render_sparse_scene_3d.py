#!/usr/bin/env python3
"""Offline interactive cuboids plus image reprojection evidence; no generated pixels."""
import argparse
import base64
import html
import itertools
import json
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from sparse_scene_3d import box_corners,project,reference_corners,CORNERS

EDGES=[(i,j) for i,j in itertools.combinations(range(8),2) if bin(i^j).count('1')==1]
PALETTE=['#1f77b4','#d62728','#2ca02c','#9467bd','#ff7f0e','#17becf','#8c564b','#e377c2']


def figure(raw,names,fid=0):
    fig=go.Figure()
    for i,e in enumerate(raw['entities']):
        state=next(s for s in e['states'] if fid in s['frame_ids']);b=state['bbox3d']
        if not b:continue
        pts=box_corners(b);xyz=[]
        for a,z in EDGES:xyz.extend([pts[a],pts[z],[None]*3])
        xs,ys,zs=zip(*xyz);name=e['entity_id']+' '+names[e['entity_id']]
        fig.add_trace(go.Scatter3d(x=xs,y=ys,z=zs,mode='lines',line=dict(color=PALETTE[i%len(PALETTE)],width=4),name=name))
    cam=next(c for c in raw['cameras'] if c['frame_id']==fid);p=cam['position_world'];t=cam['look_at_world']
    fig.add_trace(go.Scatter3d(x=[p[0],t[0]],y=[p[1],t[1]],z=[p[2],t[2]],mode='lines+markers',name='Camera / look direction',line=dict(color='black',dash='dash')))
    fig.update_layout(title=raw['shot_id']+'：独立三维盒子提案（可拖动旋转，点击图例显示/隐藏）',height=650,
        scene=dict(aspectmode='data',xaxis_title='X / reference length',yaxis_title='Y / reference length',zaxis_title='Z up / reference length'),margin=dict(l=0,r=0,t=55,b=0))
    return fig


def overlay(raw,frame,quality,variant='raw'):
    fid=frame['frame_id'];c=next(c for c in raw['cameras'] if c['frame_id']==fid)
    q=next(c for c in quality['cameras'] if c['frame_id']==fid);rt=None
    if variant=='plane_calibrated':
        if 'plane_calibrated_R_cw' not in q:return '<p>本帧没有四个可见参考角点，未做平面校验。</p>'
        rt=(np.array(q['plane_calibrated_R_cw']),np.array(q['plane_calibrated_t_cw']))
    w,h=frame['image_size'];uri='data:image/jpeg;base64,'+base64.b64encode(Path(frame['path']).read_bytes()).decode()
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" href="{uri}"/>']
    for i,e in enumerate(raw['entities']):
        b=next(s for s in e['states'] if fid in s['frame_ids'])['bbox3d']
        if b is None:continue
        uv,z=project(box_corners(b),c,rt)
        if np.any(z<=0):continue
        color=PALETTE[i%len(PALETTE)]
        for a,d in EDGES:parts.append(f'<line x1="{uv[a,0]:.2f}" y1="{uv[a,1]:.2f}" x2="{uv[d,0]:.2f}" y2="{uv[d,1]:.2f}" stroke="{color}" stroke-width="1.4"/>')
        u,v=uv.mean(axis=0);parts.append(f'<text x="{u:.2f}" y="{v:.2f}" fill="{color}" font-size="12" stroke="white" stroke-width=".3">{html.escape(e["entity_id"])}</text>')
    corners=next(r for r in raw['reference']['corners_by_frame'] if r['frame_id']==fid)
    uv,z=project(reference_corners(raw['reference']['width_ratio']),c,rt)
    for i,k in enumerate(CORNERS):
        if corners[k]['xy']:
            x,y=corners[k]['xy'];parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="yellow" stroke="black"/>')
        if z[i]>0:parts.append(f'<circle cx="{uv[i,0]:.2f}" cy="{uv[i,1]:.2f}" r="6" fill="none" stroke="cyan" stroke-width="2"/>')
    return ''.join(parts)+'</svg>'


def render(root,out):
    read=lambda p:json.loads(p.read_text())
    state=read(root/'run.json');frames={(f['shot_id'],f['frame_id']):f for f in read(root/'manifest.json')['images']}
    parts=['<!doctype html><meta charset="utf-8"><title>稀疏三维场景表征</title><style>body{font:16px sans-serif;max-width:1400px;margin:24px auto;padding:0 16px}svg{width:100%;border:1px solid #ccc}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}pre{white-space:pre-wrap} @media(max-width:800px){.pair{grid-template-columns:1fr}}</style><h1>稀疏三维场景提案与投影检查</h1><p>可旋转的图是模型推断的完整 OBB，不是实测三维真值。图像底图为未改动的原帧；彩线是三维盒子投影，黄色点是模型标出的参考角点，青色圈是其三维投影。两个 shot 尚各有局部坐标基准，不能直接对比未对齐的 XYZ。</p>']
    for i,sid in enumerate(state['shots']):
        raw=read(root/('scene_'+sid)/'response.json');g=read(root/'source_snapshot'/('graph_'+sid+'.json'));quality=read(root/('scene_'+sid)/'geometry_audit.json')
        names={e['entity_id']:e['name'] for e in g['entities']};fid=g['frames'][0]['frame_id']
        parts.append(pio.to_html(figure(raw,names,fid),full_html=False,include_plotlyjs=True if i==0 else False))
        parts.append('<p>'+html.escape(raw['reference']['x_positive_description']+' / '+raw['reference']['y_positive_description'])+'</p>')
        f=dict(frames[(sid,fid)],image_size=g['frames'][0]['image_size'])
        parts.append('<div class="pair"><div><h3>直接估计相机</h3>'+overlay(raw,f,quality,'raw')+'</div><div><h3>参考平面校验相机</h3>'+overlay(raw,f,quality,'plane_calibrated')+'</div></div>')
        parts.append('<details><summary>投影指标</summary><pre>'+html.escape(json.dumps(quality['summary'],ensure_ascii=False,indent=2))+'</pre></details>')
    out.write_text(''.join(parts))


def append_alignment_views(root,alignment_root,out):
    from sparse_scene_3d import quat_matrix,sim3
    read=lambda p:json.loads(p.read_text())
    state=read(root/'run.json');raws=[read(root/('scene_'+s)/'response.json') for s in state['shots']]
    frozen=[read(root/'source_snapshot'/('graph_'+s+'.json')) for s in state['shots']]
    identity=read(root/'source_snapshot/alignment.json');al=read(alignment_root/'alignment.json')
    maps=[{eid:g['group_id'] for g in identity['groups'] for eid in g[side+'_ids']} for side in ('a','b')]
    group_index={g['group_id']:i for i,g in enumerate(identity['groups'])}
    text='<h1>同一参考系中的两种对齐候选</h1><p>以下均以 Shot1 的坐标系显示。实线为 Shot1，虚线为 Shot3；点击图例可成组隐藏同一身份。两种候选尚未得到统一建筑参照确认，不把它们平均合并。</p>'
    for h in al['hypotheses']:
        fig=go.Figure();r=quat_matrix(h['rotation_wxyz'])
        for side,(raw,g) in enumerate(zip(raws,frozen)):
            names={e['entity_id']:e['name'] for e in g['entities']};fid=g['frames'][0]['frame_id']
            for e in raw['entities']:
                box=next(s for s in e['states'] if fid in s['frame_ids'])['bbox3d']
                if not box:continue
                pts=box_corners(box)
                if side:pts=sim3(pts,r,h['translation_xyz'],h['scale'])
                xyz=[]
                for i,j in EDGES:xyz.extend([pts[i],pts[j],[None]*3])
                x,y,z=zip(*xyz);gid=maps[side][e['entity_id']]
                fig.add_trace(go.Scatter3d(x=x,y=y,z=z,mode='lines',name=raw['shot_id']+' '+names[e['entity_id']],legendgroup=gid,
                    line=dict(color=PALETTE[group_index[gid]%len(PALETTE)],width=4,dash='dash' if side else 'solid')))
        fig.update_layout(title=h['hypothesis_id']+'：名义变换下的三维布局（未确认的对齐候选）',height=700,scene=dict(aspectmode='data',xaxis_title='Shot1 X',yaxis_title='Shot1 Y',zaxis_title='Z up'),legend=dict(groupclick='togglegroup'))
        text+=pio.to_html(fig,full_html=False,include_plotlyjs=False)+'<p>'+html.escape(h['reason'])+'</p>'
    with out.open('a') as f:f.write(text)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--alignment',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();render(a.run,a.out)
    if a.alignment:append_alignment_views(a.run,a.alignment,a.out)
