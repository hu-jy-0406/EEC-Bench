#!/usr/bin/env python3
"""Evaluate frozen Gs_global against the same visible 2D observations for all methods."""
import argparse
import base64
from collections import defaultdict
import csv
import hashlib
import html
import itertools
import json
from pathlib import Path
import numpy as np
from run_isolated_shot_static_3d import owned_compute_job

CASE=Path(__file__).resolve().parents[1]/'experiments/study_inconsistent_3'
DEFAULT=CASE/'three_method_static_3d_20260914/run01'
METHODS=['codex','boxer_codex_camera','boxer_geocalib']
NAMES={'codex':'Codex 直接3D','boxer_codex_camera':'Codex相机 + Boxer','boxer_geocalib':'GeoCalib + Boxer'}
METRICS=['iou','iou_error','edge_rmse_px','edge_rmse_over_target_diagonal','center_error_px','center_error_over_target_diagonal']


def load(p):return json.loads(p.read_text())


def project_box(box,camera):
    if box is None:return None
    signs=np.array(list(itertools.product((-1,1),repeat=3)))
    world=(signs*np.array(box['size_xyz'])/2)@np.array(box['R_world_from_object']).T+box['center_world']
    cam=(world-np.array(camera['position_world']))@np.array(camera['R_world_from_camera'])
    if not np.isfinite(cam).all() or np.any(cam[:,2]<=1e-6):return None
    uvh=cam@np.array(camera['K']).T
    return uvh[:,:2]/uvh[:,2:]


def box_metrics(projected,target,image_size):
    w,h=image_size;target=np.array(target,float);image_diag=float(np.hypot(w,h))
    clip=lambda b:np.array([np.clip(b[0],0,w),np.clip(b[1],0,h),np.clip(b[2],0,w),np.clip(b[3],0,h)],float)
    b=clip(target);target_diag=max(float(np.linalg.norm(b[2:]-b[:2])),1.)
    if projected is None:
        return dict(iou=0.,iou_error=1.,edge_rmse_px=image_diag,edge_rmse_over_target_diagonal=image_diag/target_diag,
                    center_error_px=image_diag,center_error_over_target_diagonal=image_diag/target_diag,
                    invalid_projection=True,projected_envelope_raw=None,projected_envelope_clipped=None)
    raw=np.r_[projected.min(0),projected.max(0)];a=clip(raw)
    area=lambda x:float(np.prod(np.maximum(x[2:]-x[:2],0)))
    intersection=area(np.r_[np.maximum(a[:2],b[:2]),np.minimum(a[2:],b[2:])]);union=area(a)+area(b)-intersection
    iou=intersection/union if union>0 else 0.
    edge=float(np.sqrt(np.mean((a-b)**2)));center=float(np.linalg.norm((a[:2]+a[2:]-b[:2]-b[2:])/2))
    return dict(iou=iou,iou_error=1-iou,edge_rmse_px=edge,edge_rmse_over_target_diagonal=edge/target_diag,
                center_error_px=center,center_error_over_target_diagonal=center/target_diag,
                invalid_projection=False,projected_envelope_raw=raw.tolist(),projected_envelope_clipped=a.tolist())


def mean_metrics(rows):
    return {k:float(np.mean([r[k] for r in rows])) for k in METRICS}


def aggregate(rows):
    entities=defaultdict(list)
    for r in rows:entities[(r['method'],r['shot_id'],r['entity_id'])].append(r)
    per_entity=[dict(method=m,shot_id=s,entity_id=e,n_frames=len(rs),**mean_metrics(rs)) for (m,s,e),rs in entities.items()]
    per_shot=[];overall=[]
    for method in METHODS:
        shot_rows=[]
        for sid in ['shot1','shot3']:
            es=[r for r in per_entity if r['method']==method and r['shot_id']==sid]
            observations=[r for r in rows if r['method']==method and r['shot_id']==sid]
            shot=dict(method=method,shot_id=sid,n_entities=len(es),n_observations=len(observations),
                      invalid_projections=sum(r['invalid_projection'] for r in observations),**mean_metrics(es))
            shot['micro_observation_mean']=mean_metrics(observations)
            per_shot.append(shot);shot_rows.append(shot)
        overall.append(dict(method=method,**mean_metrics(shot_rows),
                            all_entities_equal_mean=mean_metrics([e for e in per_entity if e['method']==method]),
                            all_observations_equal_mean=mean_metrics([r for r in rows if r['method']==method])))
    winners=CounterLike()
    for sid,eid in sorted({(e['shot_id'],e['entity_id']) for e in per_entity}):
        es=[e for e in per_entity if e['shot_id']==sid and e['entity_id']==eid];best=max(e['iou'] for e in es)
        names=[e['method'] for e in es if abs(e['iou']-best)<1e-9]
        winners.add(names)
    return dict(primary_aggregation='mean over visible frames per entity, then equal entities within shot, then equal two shots',
                primary_metric='iou_error = 1 - clipped envelope IoU; lower is better',per_entity=per_entity,per_shot=per_shot,
                overall=overall,best_primary_method=min(overall,key=lambda r:r['iou_error'])['method'],entity_iou_wins=winners.result)


class CounterLike:
    def __init__(self):self.result={m:0 for m in METHODS};self.result['ties']=0
    def add(self,names):self.result[names[0] if len(names)==1 else 'ties']+=1


def report(out,summary,rows,images):
    lines=['# Gs_global 原相机视角的重投影框误差','',
        '冻结三种方法的最终融合Gs_global，不重新拟合、不调相机。使用相同独立静止划分和所有可见实体帧，包括融合时被舍弃的帧及低支持框。',
        '', '主指标为1−IoU；先对每个实体的可见帧平均，再对shot内实体平均，最后两个shot等权。',
        '', '| 方法 | Shot1平均IoU↑ | Shot3平均IoU↑ | 两shot平均IoU↑ | 1−IoU↓ | 边界RMSE(px)↓ | 中心偏差(px)↓ |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for r in summary['overall']:
        shots=[s for s in summary['per_shot'] if s['method']==r['method']]
        lines.append('| '+ ' | '.join([NAMES[r['method']],f'{shots[0]["iou"]:.4f}',f'{shots[1]["iou"]:.4f}',f'{r["iou"]:.4f}',f'{r["iou_error"]:.4f}',f'{r["edge_rmse_px"]:.2f}',f'{r["center_error_px"]:.2f}'])+' |')
    lines += ['', '**主指标最优：'+NAMES[summary['best_primary_method']]+'。**',
        '', '三维框8个角点由中心/尺寸/旋转重新计算，以各自相机R、位置和K投影；取2D包围框，裁切至852×480图像范围后与冻结2D框比较。边界RMSE为四个xyxy坐标差的均方根，中心偏差为两框中心的欧氏距离。还记录除以目标框对角线的归一化误差。不是具备真实角点对应的经典重投影误差。',
        '', '样本：Shot1的17个静止实体、96个可见实体帧；Shot3的21个静止实体、125个可见实体帧。每种方法共221个，三种方法共663项，逐项样本键完全一致。缺失/无效/相机后方投影计IoU=0，边界及中心误差按图像对角线惩罚；本次实际无效数量见summary.json。',
        '', '结论范围：这是对现有2D框的样本内拟合比较。2D框是Boxer输入，且融合权重也使用了投影IoU；不是独立留出测试、人工真值或3D精度评估。遮挡时完整3D物体包络与可见2D框的语义也可能不同。三种方法使用各自原相机，因此比较的是相机+几何组合，不能单独归因于几何生成器。',
        '', '[逐帧原图投影查看页](reprojection.html) · [完整汇总](summary.json) · [逐实体帧CSV](observations.csv)',
        '', '统计同时保存每个实体/shot结果、所有221观察等权和所有38实体等权的敏感性汇总，不按各方法自身保留帧筛样本。']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    # Self-contained original-pixel visual check. Frame arrays remain fixed source observations.
    brief=[{k:r[k] for k in ('method','shot_id','frame_id','entity_id','name','target_box','projected_corners','iou','edge_rmse_px','center_error_px')} for r in rows]
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gs_global 重投影对比</title><style>body{font:15px system-ui;background:#f4f7fb;color:#182a40;margin:22px}main{max-width:1200px;margin:auto}svg{width:100%;background:#ddd}select,label{margin:8px;padding:6px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}</style><main><h1>同一帧：最终 Gs_global 的相机投影</h1><p>绿色为冻结二维框；三种颜色为融合后的三维框投影。可切换实体，并开关各方法。分数比较裁切后的二维包围框，不是真实角点误差。</p><select id="shot"></select><select id="frame"></select><select id="entity"></select><div id="toggles"></div><svg id="image" viewBox="0 0 852 480"></svg><table id="metrics"></table></main><script>
const DATA=__DATA__,IMAGES=__IMAGES__,NAMES=__NAMES__,COLORS=['#ed8615','#da3cac','#05b8e6'],METHODS=Object.keys(NAMES),$=id=>document.getElementById(id);
for(const s of ['shot1','shot3'])$('shot').add(new Option(s,s));for(const f of [0,24,48,72,96,120])$('frame').add(new Option(f,f));
METHODS.forEach((m,i)=>{const l=document.createElement('label'),b=document.createElement('input');b.type='checkbox';b.checked=true;b.id='show'+i;b.onchange=draw;l.style.color=COLORS[i];l.append(b,document.createTextNode(NAMES[m]));$('toggles').append(l)});
function refresh(){const es=DATA.filter(r=>r.shot_id==$('shot').value&&r.frame_id==+$('frame').value&&r.method==METHODS[0]),prev=$('entity').value;$('entity').innerHTML='';es.forEach(e=>$('entity').add(new Option(e.entity_id+' '+e.name,e.entity_id)));if(es.some(e=>e.entity_id==prev))$('entity').value=prev;draw()}
function draw(){const rows=DATA.filter(r=>r.shot_id==$('shot').value&&r.frame_id==+$('frame').value&&r.entity_id==$('entity').value);if(!rows.length)return;const b=rows[0].target_box;let svg=`<image href="${IMAGES[$('shot').value+'/'+$('frame').value]}" width="852" height="480"/><rect x="${b[0]}" y="${b[1]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="none" stroke="#22df52" stroke-width="3"/>`,table='<tr><th>方法</th><th>IoU↑</th><th>边界RMSE(px)↓</th><th>中心误差(px)↓</th></tr>';rows.forEach(r=>{const i=METHODS.indexOf(r.method);table+=`<tr><td>${NAMES[r.method]}</td><td>${r.iou.toFixed(3)}</td><td>${r.edge_rmse_px.toFixed(2)}</td><td>${r.center_error_px.toFixed(2)}</td></tr>`;if(!$('show'+i).checked||!r.projected_corners)return;const p=r.projected_corners;for(let a=0;a<8;a++)for(let z=a+1;z<8;z++)if([1,2,4].includes(a^z))svg+=`<line x1="${p[a][0]}" y1="${p[a][1]}" x2="${p[z][0]}" y2="${p[z][1]}" stroke="${COLORS[i]}" stroke-width="1.7"/>`});$('image').innerHTML=svg;$('metrics').innerHTML=table}
$('shot').onchange=refresh;$('frame').onchange=refresh;$('entity').onchange=draw;refresh();</script></html>'''
    for key,value in [('__DATA__',brief),('__IMAGES__',images),('__NAMES__',NAMES)]:page=page.replace(key,json.dumps(value,ensure_ascii=False).replace('</','<\\/'))
    (out/'reprojection.html').write_text(page)


def run(root):
    job=owned_compute_job();out=root/'reprojection_evaluation';out.mkdir(exist_ok=True);rows=[];sources=[];images={}
    labels=CASE/'shot_static_3d_isolated_20260914/run01'
    for sid in ['shot1','shot3']:
        source_path=labels/sid/'source_shot.json';review_path=labels/sid/'agent_review.json';source=load(source_path)['shots'][0]
        static={e['entity_id'] for e in load(review_path)['shots'][0]['entities'] if e['status']=='static'};sources += [source_path,review_path]
        for f in source['calibration']['images']:
            path=Path(f['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
            images[sid+'/'+str(f['frame_id'])]='data:image/jpeg;base64,'+base64.b64encode(path.read_bytes()).decode()
        for method in METHODS:
            path=root/method/sid/'Gs_global.json';sources.append(path);g=load(path);nodes={e['entity_id']:e for e in g['entities']};cams={c['frame_id']:c for c in g['cameras']}
            assert set(nodes)==static
            for e in source['entities']:
                if e['entity_id'] not in static:continue
                for obs in e['observations']:
                    if not obs['visible']:continue
                    assert obs['box_xyxy'] is not None
                    fid=obs['frame_id'];uv=project_box(nodes[e['entity_id']]['geometry'],cams[fid]);metrics=box_metrics(uv,obs['box_xyxy'],cams[fid]['image_size'])
                    rows.append(dict(method=method,shot_id=sid,entity_id=e['entity_id'],name=e['name'],frame_id=fid,target_box=obs['box_xyxy'],
                                     projected_corners=uv.tolist() if uv is not None else None,**metrics))
    keys=[{(r['shot_id'],r['entity_id'],r['frame_id']) for r in rows if r['method']==m} for m in METHODS]
    assert keys[0]==keys[1]==keys[2] and all(sum(r['method']==m for r in rows)==len(keys[0]) for m in METHODS)
    result=aggregate(rows);result.update(allocation=job,observations_per_method=len(keys[0]),total_observations=len(rows),
        provenance=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources],
        paired_sample_audit='pass: all methods use exact same entity-frame keys',new_model_calls=0,
        test_scope='in-sample 2D box reprojection fit of frozen final Gs_global, not independent 3D accuracy')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'observations.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    with (out/'observations.csv').open('w',newline='') as f:
        fields=['method','shot_id','entity_id','name','frame_id',*METRICS,'invalid_projection'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in rows)
    report(out,result,rows,images);print(json.dumps(dict(best=result['best_primary_method'],overall=result['overall'],shots=result['per_shot'],wins=result['entity_iou_wins']),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,default=DEFAULT);run(p.parse_args().run)
