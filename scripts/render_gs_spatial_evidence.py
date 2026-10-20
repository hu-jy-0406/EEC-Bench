#!/usr/bin/env python3
"""Offline paired original-frame evidence and numeric relation intervals."""
import argparse,base64,hashlib,json
from pathlib import Path
import numpy as np
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import read,save

def render(root):
    owned_compute_job();graphs=[read(root/'source_snapshot'/n) for n in ['graph_a.json','graph_b.json']];matching=read(root/'source_snapshot/matching.json');manifest=read(root/'source_snapshot/manifest.json');images={};sizes={}
    for g,row in zip(graphs,manifest['sources'][2:]):
        s=read(Path(row['path']))['shots'][0]
        for f in s['calibration']['images']:
            raw=Path(f['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==f['sha256'];key=g['shot_id']+'/'+str(f['frame_id']);images[key]='data:image/jpeg;base64,'+base64.b64encode(raw).decode();sizes[key]=next(c['image_size'] for c in g['cameras'] if c['frame_id']==f['frame_id'])
    relations=read(root/'relation_opportunities.json')['relations'];groupmap={g['group_id']:g for g in matching['groups']};projected={}
    for relation in relations:
        arr=[]
        for i,(g,side) in enumerate(zip(graphs,['a','b'])):
            nodes={e['entity_id']:e for e in g['entities']};centers=[np.array(nodes[groupmap[x][side+'_ids'][0]]['geometry']['center_world']) for x in relation['endpoint_groups']];mid=sum(centers)/2;m=relation['measurements'][i]
            directions={}
            if m['status']=='measured':
                axis=np.array(m['basis_world'])[:,relation['axis_index']]
                for cam in g['cameras']:
                    points=np.array([mid,mid+axis*.1*m['anchor_baseline']]);pc=(points-cam['position_world'])@np.array(cam['R_world_from_camera']);uv=pc@np.array(cam['K']).T
                    if np.all(pc[:,2]>0):
                        uv=uv[:,:2]/uv[:,2:];d=uv[1]-uv[0];length=np.linalg.norm(d)
                        if length>1e-7:directions[str(cam['frame_id'])]=(d/length).tolist()
            arr.append(directions)
        projected[relation['relation_id']]=arr
    data=dict(score=read(root/'score.json'),graphs=graphs,matching=matching,relations=relations,images=images,sizes=sizes,projected_directions=projected)
    encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gs 空间关系冲突</title><style>
body{max-width:1450px;margin:24px auto;padding:0 20px;font:16px system-ui;color:#172333;background:#f5f7fb}.card{padding:18px;background:white;margin:14px 0;border-radius:10px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}.muted{color:#596979;font-size:14px}svg{display:block;width:100%;height:auto}select{padding:8px;max-width:100%;font:inherit}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}p{line-height:1.5}h1{font-size:27px}@media(max-width:900px){.cols{grid-template-columns:1fr}}</style>
<h1>Gs：存在性与空间关系冲突</h1><div id="summary" class="card"></div><div class="card"><select id="select"></select><p>参考轴由同一对参考物与物理向上方向计算。数值为两物体中心沿该轴的差，除以参考物水平间距；相机原点、正尺度与坐标旋转不会改变其符号。</p><p class="muted">这不是全房间配准。红框为第一个物体，蓝框为第二个物体，黄框为审核引用的参考区域；箭头只显示 Gs 给出的正轴投影方向。几何压力区间不是统计置信区间。</p></div><div id="detail"></div>
<script type="application/json" id="data">DATA</script><script>
const D=JSON.parse(document.getElementById('data').textContent),S=D.score,ns='http://www.w3.org/2000/svg';const labels={conflict:'确认空间冲突',unknown:'未确认冲突',compatible:'相容'},axisnames={cross_anchor_up:'u：参考方向 × 向上',toward_reference:'v：朝向参考物',vertical:'z：向上'};
const names={},groups={};for(const g of D.graphs)for(const e of g.entities)names[e.entity_id]=e.name;for(const g of D.matching.groups)groups[g.group_id]=g;
function el(t,text,cls){const n=document.createElement(t);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}function sv(t,attrs){const n=document.createElementNS(ns,t);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n}function groupname(id){return names[groups[id].a_ids[0]]}
const fmt=(x,d=2)=>x===null?'不可判定':x.toFixed(d);const top=document.getElementById('summary');top.append(el('h2','主分数（上界） '+fmt(S.score)+' / 100 · 原分数 '+fmt(S.previous_score)));top.append(el('p','确认空间关系冲突 '+S.confirmed_relation_count+' 项；冲突参与实体 '+S.weights.conflict+'，相容 '+S.weights.compatible+'，未知 '+S.weights.unknown+'，互补 '+S.weights.complement+'。覆盖率 '+fmt(S.coverage===null?null:100*S.coverage,1)+'%。'));
top.append(el('p','确认冲突关系的两个端点各作为一个参与冲突的实体计分，每个实体最多扣一次。这不证明两者都移动，也不证明精确交换位置。存在性结论和原始 Gs 保留。','muted'));
const sel=document.getElementById('select');for(const r of S.spatial_relations){const op=el('option',labels[r.status]+' · '+r.endpoint_groups.map(groupname).join(' ↔ ')+' · '+axisnames[r.axis]);op.value=r.relation_id;sel.append(op)}
function intervalPlot(r,i){if(r.sensitivity_intervals[i]===null)return el('p','几何证据不足，保留未知。');const vals=r.sensitivity_intervals.flat().filter(x=>x!==null),span=Math.max(...vals.map(Math.abs),.02)*1.15,px=x=>250+210*x/span;const s=sv('svg',{viewBox:'0 0 500 110'});s.append(sv('line',{x1:35,y1:55,x2:465,y2:55,stroke:'#8190a5'}));s.append(sv('line',{x1:250,y1:20,x2:250,y2:85,stroke:'#8190a5','stroke-dasharray':'4 3'}));const [lo,hi]=r.sensitivity_intervals[i];s.append(sv('rect',{x:px(lo),y:40,width:Math.max(1,px(hi)-px(lo)),height:30,fill:i?'#458dc4':'#d95362',opacity:.55}));s.append(sv('circle',{cx:px(r.nominal[i]),cy:55,r:6,fill:'#172333'}));const t=sv('text',{x:250,y:105,'text-anchor':'middle','font-size':14});t.textContent='r = '+r.nominal[i].toFixed(4)+'；压力区间 ['+lo.toFixed(4)+', '+hi.toFixed(4)+']';s.append(t);return s}
function frame(r,w,i){const shot=S.shots[i],key=shot+'/'+w.frame_id,[W,H]=D.sizes[key],s=sv('svg',{viewBox:'0 0 '+W+' '+H});s.append(sv('image',{href:D.images[key],width:W,height:H}));for(const [k,c]of [['reference_region_xyxy','#e9ac21'],['subject_region_xyxy','#ed354e'],['object_region_xyxy','#328de5']]){const [x,y,x2,y2]=w[k];s.append(sv('rect',{x,y,width:x2-x,height:y2-y,fill:'none',stroke:c,'stroke-width':k.startsWith('reference')?2:3}))}const d=D.projected_directions[r.relation_id][i][String(w.frame_id)];if(d){const x=W*.16,y=H*.76,ex=x+65*d[0],ey=y+65*d[1];s.append(sv('line',{x1:x,y1:y,x2:ex,y2:ey,stroke:'#12bcc9','stroke-width':5}));const p1=[ex-12*d[0]-6*d[1],ey-12*d[1]+6*d[0]],p2=[ex-12*d[0]+6*d[1],ey-12*d[1]-6*d[0]];s.append(sv('polygon',{points:[[ex,ey],p1,p2].map(x=>x.join(',')).join(' '),fill:'#12bcc9'}));const t=sv('text',{x:x+8,y:y-15,fill:'#006670',stroke:'white','stroke-width':.3,'font-size':18});t.textContent=r.axis==='cross_anchor_up'?'u+':r.axis==='toward_reference'?'v+':'z+';s.append(t)}return s}
function show(){const r=S.spatial_relations.find(x=>x.relation_id===sel.value),raw=D.relations.find(x=>x.relation_id===sel.value),dest=document.getElementById('detail');dest.replaceChildren();const info=el('div',undefined,'card');info.append(el('h2',labels[r.status]+' · '+axisnames[r.axis]));info.append(el('p','参考物：'+r.anchor_groups.map(groupname).join(' → ')));if(r.verification){info.append(el('p',r.verification.reason));info.append(el('p',r.verification.remaining_alternatives,'muted'))}else info.append(el('p','数值压力区间未证明反转，因此本轴不增加罚分。'));dest.append(info);const cols=el('div',undefined,'cols');for(let i=0;i<2;i++){const card=el('div',undefined,'card');card.append(el('h2',S.shots[i]));card.append(intervalPlot(r,i));const o=raw.shot_observations[i];card.append(el('p','单 shot 判断：'+o.order+'。'+o.reason));const ws=r.verification?r.verification[i?'witnesses_b':'witnesses_a']:o.evidence;for(const w of ws){card.append(el('h3','Frame '+w.frame_id));card.append(frame(r,w,i));card.append(el('p',w.observation))}cols.append(card)}dest.append(cols);const detail=el('details',undefined,'card');detail.append(el('summary','完整计算与门控数据'));detail.append(el('pre',JSON.stringify({scoring:r,geometry:raw},null,2)));dest.append(detail)}
sel.onchange=show;if(S.spatial_relations.length){sel.value=(S.spatial_relations.find(x=>x.status==='conflict')||S.spatial_relations[0]).relation_id;show()}else{sel.disabled=true;document.getElementById('detail').append(el('p','没有通过共同支撑面检查的空间关系，保留原有评分，不增加空间罚分。'))}
</script></html>'''.replace('DATA',encoded)
    (root/'evidence.html').write_text(page);save(root/'visualization_data.json',dict(projected_axis_directions=projected,images=len(images),relations=len(relations),browser_executed=False));print(str(root/'evidence.html'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);render(p.parse_args().run.resolve())
