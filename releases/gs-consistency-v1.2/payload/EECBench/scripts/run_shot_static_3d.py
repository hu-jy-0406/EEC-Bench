#!/usr/bin/env python3
"""Bounded static-shot pilot. Labels are explicit visual-agent reviews, never thresholds."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/study_inconsistent_3/geocalib_boxer_20260913/boxer_scene_graph.json'
OUT = ROOT / 'experiments/study_inconsistent_3/shot_static_3d_20260914'
SIGNS = np.array(list(itertools.product([-1, 1], repeat=3)))

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def corners(center, size, rotation):
    return SIGNS * np.asarray(size) / 2 @ np.asarray(rotation).T + center

def canonical(g):
    """Choose the long horizontal axis; quotient out 90-degree XY swaps and 180 flips."""
    size = np.asarray(g['size_xyz'], float).copy()
    r = np.asarray(g['R_world_from_object'], float)
    yaw = np.arctan2(r[1, 0], r[0, 0])
    if size[1] > size[0]:
        size[[0, 1]] = size[[1, 0]]
        yaw += np.pi / 2
    return np.asarray(g['center_world'], float), size, yaw % np.pi

def fuse(states):
    valid = [s for s in states if s['geometry'] is not None]
    if not valid:
        raise ValueError('No finite 3D observations')
    cs, ss, ys = zip(*(canonical(s['geometry']) for s in valid))
    cs, ss, ys = np.array(cs), np.array(ss), np.array(ys)
    # Circular medoid on RP1 chooses an orientation anchor only; final angle
    # and center/size are median estimates using every valid frame.
    delta = (ys[:, None] - ys[None, :] + np.pi/2) % np.pi - np.pi/2
    anchor = ys[np.argmin(np.abs(delta).sum(axis=1))]
    unwrapped = anchor + (ys - anchor + np.pi/2) % np.pi - np.pi/2
    yaw = float(np.median(unwrapped))
    c, size = np.median(cs, axis=0), np.median(ss, axis=0)
    r = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    dev = np.degrees(np.abs(unwrapped - yaw))
    geom = dict(center_world=c.tolist(), size_xyz=size.tolist(), R_world_from_object=r.tolist(),
                corners_world=corners(c, size, r).tolist())
    agg = dict(method='all-visible-frame coordinatewise median; long-XY-axis canonicalization; modulo-pi circular-medoid unwrap and median yaw',
               source_frame_ids=[s['frame_id'] for s in valid], source_count=len(valid),
               center_mad_xyz=np.median(np.abs(cs-c), axis=0).tolist(),
               center_range_xyz=np.ptp(cs, axis=0).tolist(),
               size_mad_xyz=np.median(np.abs(ss-size), axis=0).tolist(),
               size_range_xyz=np.ptp(ss, axis=0).tolist(), yaw_deviation_deg=dev.tolist(),
               source_center_world=cs.tolist(), source_canonical_size_xyz=ss.tolist(),
               source_canonical_yaw_deg=np.degrees(ys).tolist(),
               orientation_ambiguous_near_square=bool(size[0]/size[1] < 1.15),
               dispersion_is_not_calibrated_confidence=True)
    return geom, agg

def diagnostics(source):
    rows = []
    for s in source['shots']:
        for e in s['entities']:
            _, agg = fuse(e['states'])
            boxes = [o['box_xyxy'] for o in e['observations'] if o['box_xyxy'] is not None]
            rows.append(dict(entity_id=e['entity_id'], name=e['name'],
                             box_range_xyxy=np.ptp(boxes, axis=0).tolist(), observations=e['observations'],
                             geometry_dispersion=agg))
    return dict(entities=rows)

def build(source, review):
    review_shots = {s['shot_id']: s for s in review['shots']}
    if set(review_shots) != {s['shot_id'] for s in source['shots']}:
        raise ValueError('Shot review coverage mismatch')
    shots=[]
    for s in source['shots']:
        labels=review_shots[s['shot_id']]['entities']
        if len(labels)!=len(s['entities']) or {r['entity_id'] for r in labels}!={e['entity_id'] for e in s['entities']}:
            raise ValueError('Review must cover every entity exactly once')
        label={r['entity_id']:r for r in labels}
        coord=s['calibration']['fixed_camera_consensus']
        for frame in s['frames']:
            if frame['R_world_from_camera'] != coord['R_world_from_camera'] or frame['translation_world_from_camera'] != [0,0,0]:
                raise ValueError('This pilot requires existing same fixed camera transform')
        nodes=[]
        for e in s['entities']:
            r=label[e['entity_id']]
            if r['status'] not in ('static','moving','unknown'):
                raise ValueError('Invalid status')
            if r['status'] != 'static':
                continue
            if r['motion_intervals']:
                raise ValueError('Any observed movement excludes a static node')
            if sum(st['geometry'] is not None for st in e['states']) < 2:
                raise ValueError('Static shot fusion requires at least two geometry observations')
            g,a=fuse(e['states'])
            nodes.append(dict(entity_id=e['entity_id'],name=e['name'],status='static',geometry=g,
                              aggregation=a,uncertainty=dict(visual=r['uncertainty'],
                              geometry='Monocular prior depth and independent per-frame lifting; occlusion can bias whole-box extent; fusion does not repair systematic depth or establish metric truth.',
                              sparse_time='Static on supplied six keyframes; unobserved instants are not certified.')))
        shots.append(dict(shot_id=s['shot_id'],world_frame_id=s['world_frame_id'],scale=s['scale'],
                          coordinate_system=dict(origin='camera center',handedness='right',
                          axes='X approximately image-right; Y horizontal camera-forward; Z gravity-up',
                          R_world_from_camera=coord['R_world_from_camera'],translation_world_from_camera=[0,0,0],
                          registration='shot-local only; no cross-shot alignment'),
                          source_frame_ids=[f['frame_id'] for f in s['frames']],entities=nodes))
    return dict(schema_version='shot_static_3d_v0.1',shots=shots)

def viewer(graph):
    data=json.dumps(graph,ensure_ascii=False).replace('</','<\\/')
    return '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>Shot 静态 3D 结构</title>
<style>body{margin:0;background:#111827;color:#eee;font:15px system-ui}header{padding:16px}canvas{width:75vw;height:78vh;background:#0b1220}aside{position:absolute;right:0;top:110px;width:23vw;max-height:75vh;overflow:auto;font-size:13px}button,select{padding:6px}pre{white-space:pre-wrap}label{display:block;margin:8px}</style>
<header><b>每个 Shot 一个静态 3D 图</b> <select id="shot"></select> <button id="reset">重置视角</button><br>拖动旋转；滚轮缩放；勾选物体。红 X / 绿 Y / 蓝 Z；原点为相机中心。坐标是模型先验尺度，未标定，未跨 Shot 配准。</header>
<canvas id="c"></canvas><aside id="list"></aside><script>const DATA='''+data+''';
const C=document.getElementById('c'),ctx=C.getContext('2d'),S=document.getElementById('shot'),L=document.getElementById('list');let yaw=.55,pitch=.5,zoom=1,drag=null,active;
DATA.shots.forEach((s,i)=>S.add(new Option(s.shot_id,i)));const edges=[];for(let i=0;i<8;i++)for(let j=i+1;j<8;j++)if([1,2,4].includes(i^j))edges.push([i,j]);
function choose(){active=DATA.shots[+S.value];L.innerHTML='';active.entities.forEach((e,i)=>{let l=document.createElement('label'),b=document.createElement('input');b.type='checkbox';b.checked=true;b.onchange=draw;l.append(b,document.createTextNode(e.entity_id+' '+e.name));l.title=JSON.stringify(e.geometry,null,2);L.append(l)});draw()}
function draw(){C.width=C.clientWidth*devicePixelRatio;C.height=C.clientHeight*devicePixelRatio;let w=C.width,h=C.height;ctx.clearRect(0,0,w,h);let pts=active.entities.flatMap(e=>e.geometry.corners_world);let lo=[0,1,2].map(k=>Math.min(0,...pts.map(p=>p[k]))),hi=[0,1,2].map(k=>Math.max(0,...pts.map(p=>p[k]))),mid=lo.map((v,k)=>(v+hi[k])/2),scale=Math.min(w,h)*.67/Math.max(...hi.map((v,k)=>v-lo[k]))*zoom;
function project(p){let [x,y,z]=p.map((v,k)=>v-mid[k]),xx=Math.cos(yaw)*x-Math.sin(yaw)*y,yy=Math.sin(yaw)*x+Math.cos(yaw)*y;return [w/2+xx*scale,h/2+(Math.sin(pitch)*yy-Math.cos(pitch)*z)*scale]}
function line(a,b,color,width=1){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(...project(a));ctx.lineTo(...project(b));ctx.stroke()}
active.entities.forEach((e,i)=>{if(!L.children[i].firstChild.checked)return;let color=`hsl(${i*137.5%360} 75% 68%)`;edges.forEach(([a,b])=>line(e.geometry.corners_world[a],e.geometry.corners_world[b],color,1.5));let p=project(e.geometry.center_world);ctx.fillStyle=color;ctx.font=`${12*devicePixelRatio}px system-ui`;ctx.fillText(e.entity_id,...p)});let len=Math.max(...hi.map((v,k)=>v-lo[k]))*.17;['#f87171','#4ade80','#60a5fa'].forEach((color,k)=>{let p=[0,0,0];p[k]=len;line([0,0,0],p,color,3);ctx.fillStyle=color;ctx.fillText('XYZ'[k],...project(p))});}
C.onpointerdown=e=>{drag=[e.clientX,e.clientY];C.setPointerCapture(e.pointerId)};C.onpointerup=()=>drag=null;C.onpointermove=e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.01;pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.clientY-drag[1])*.01));drag=[e.clientX,e.clientY];draw()};C.onwheel=e=>{e.preventDefault();zoom=Math.max(.2,Math.min(8,zoom*Math.exp(-e.deltaY*.001)));draw()};S.onchange=choose;document.getElementById('reset').onclick=()=>{yaw=.55;pitch=.5;zoom=1;draw()};window.onresize=draw;choose();</script></html>'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--diagnostics-only',action='store_true');a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);source=json.loads(SOURCE.read_text())
    dump(OUT/'diagnostics.json',diagnostics(source))
    if a.diagnostics_only:return
    review=json.loads((OUT/'agent_review.json').read_text());graph=build(source,review)
    paths=[SOURCE,OUT/'agent_review.json']
    for s in source['shots']:
        paths += [Path(f['path']) for f in s['calibration']['images']]
        paths.append(ROOT/'experiments/study_inconsistent_3/wedetect_shot_entities_20260912/run01/shots'/s['shot_id']/'entities.json')
    graph['provenance']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    dump(OUT/'static_scene_graph.json',graph);(OUT/'viewer.html').write_text(viewer(graph))
    summary=dict(shots=[dict(shot_id=s['shot_id'],counts={k:sum(e['status']==k for e in s['entities']) for k in ('static','moving','unknown')}) for s in review['shots']],
                 graphs=len(graph['shots']),entity_reviews=sum(len(s['entities']) for s in review['shots']),
                 configured_cli_calls=0,reviewer='current delegated Codex agent; all 12 original images directly viewed',
                 gpu_calls=0,execution='owned allocation185272/node241; one CPU',tests='see tests.txt',browser_runtime_validated=False)
    dump(OUT/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
