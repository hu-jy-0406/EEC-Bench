#!/usr/bin/env python3
"""Offline evidence viewer; original RGB images are display-only inputs."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def render(root,frames_root):
    load=lambda p:json.loads(p.read_text())
    summary=load(root/'summary.json');run=load(root/'matching.json')
    graphs=[load(root/f'{s}_relations.json') for s in summary['shot_ids']]
    slots=load(root/'global_slots.json')['slots']
    source=load(Path(summary['input_path']))
    photos={};photo_manifest=[]
    for sh in source['shots']:
        for f in sh['frames']:
            p=frames_root/sh['shot_id']/f'frame_{f["frame_id"]:06d}.jpg'
            raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            assert digest==f['image_sha256'],f'Frame changed: {p}'
            photos[f'{sh["shot_id"]}:{f["frame_id"]}']='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
            photo_manifest.append(dict(path=str(p.resolve()),sha256=digest,used_for='display_only'))
    names={node['entity_id']:node['name'] for g in graphs for node in g['nodes']}
    display_graphs=[{k:g[k] for k in ['shot_id','nodes','frames','edges','descriptors']} for g in graphs]
    data=json.dumps(dict(summary=summary,run=run,graphs=display_graphs,slots=slots,photos=photos),ensure_ascii=False).replace('</','<\\/')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>Shot1 / Shot3 关系槽位匹配</title>
<style>body{font:15px system-ui;margin:24px;color:#193146;background:#f1f5f8}h1{font-size:25px}p{line-height:1.6}
.panel{background:white;border-radius:9px;padding:14px;margin:12px 0}.views{display:grid;grid-template-columns:1fr 1fr;gap:14px}
canvas{width:100%;background:#fafafa}select,button{padding:7px;margin:5px}table{border-collapse:collapse;width:100%;background:white}
th,td{text-align:left;padding:8px;border-bottom:1px solid #dce4eb}tr{cursor:pointer}tr:hover,tr.active{background:#e3eff9}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.stable{color:#177b66}.ambiguous{color:#b16a13}.unmatched{color:#79628e}
#tablewrap{max-height:520px;overflow:auto}.small{font-size:12px;color:#65717a}@media(max-width:800px){.views{grid-template-columns:1fr}}
</style><h1>Shot1 / Shot3：基于关系的全局槽位候选</h1>
<p>仅使用实体逐帧三维几何进行匹配；原图和名字仅用于展示。最佳解是结构候选，不是已验证物理身份。
“稳定”仅指本次搜索和敏感性检查。未匹配不等于删除或新增；本轮没有计算 S_EC / S_RC。</p>
<div class="panel" id="summary"></div><label>全局候选解 <select id="solution"></select></label><span id="transform"></span>
<div class="views"><div class="panel"><strong>Shot1</strong><select id="frame0"></select><canvas id="image0"></canvas></div>
<div class="panel"><strong>Shot3</strong><select id="frame1"></select><canvas id="image1"></canvas></div></div>
<p class="small">橙色：当前行实体；蓝色：当前候选骨架。点击表格切换查看。没有可见框时不补造框。</p>
<div id="tablewrap"><table><thead><tr><th>槽位</th><th>Shot1</th><th>Shot3</th><th>状态</th></tr></thead><tbody id="rows"></tbody></table></div>
<details open class="panel"><summary>当前对应的关系证据 / 冲突 / 替代解释</summary><pre id="detail"></pre></details>
<div class="panel"><h3>候选解的骨架对应</h3><pre id="backbone"></pre></div>
<p><a href="README.md">完整报告</a> · <a href="global_slots.json">槽位 JSON</a> · <a href="matching.json">骨架与全图求解 JSON</a> · <a href="summary.json">运行与输入记录</a></p>
<script>
const D=__DATA__,$=id=>document.getElementById(id);let current=null,activeRows=[],solutionIndex=0;
const words={stable_structural_candidate:'本次检查稳定的结构候选',ambiguous_structural_candidate:'歧义 / 支持不足',unmatched_in_shot3:'Shot3 未匹配',unmatched_in_shot1:'Shot1 未匹配',candidate:'备选解中的对应',geometry_unreliable:'无可靠骨架'};
function node(id){return D.graphs.flatMap(g=>g.nodes).find(n=>n.entity_id===id)}
function label(id){return id?`${id} · ${node(id)?.name||''}`:'—'}
function rowsForSolution(k){if(k===0)return D.slots;let r=D.run.solutions[k],used=new Set();let rows=D.graphs[0].nodes.map((e,i)=>{let p=r.mapping.find(x=>x[0]===i);if(p)used.add(p[1]);return {slot_id:'alt'+(i+1),source:e.entity_id,target:p?D.graphs[1].nodes[p[1]].entity_id:null,status:p?'candidate':'unmatched_in_shot3'}});D.graphs[1].nodes.forEach((e,j)=>{if(!used.has(j))rows.push({slot_id:'alt'+(rows.length+1),source:null,target:e.entity_id,status:'unmatched_in_shot1'})});return rows}
function draw(k){let g=D.graphs[k],fid=Number($('frame'+k).value),im=new Image(),c=$('image'+k),ctx=c.getContext('2d');let row=current,sol=D.run.solutions[solutionIndex];
im.onload=()=>{if(row!==current||fid!==Number($('frame'+k).value))return;c.width=im.width;c.height=im.height;ctx.drawImage(im,0,0);
let target=k===0?row?.source:row?.target;let anchors=new Set((sol?.hypothesis.anchors||[]).map(p=>g.nodes[p[k]].entity_id));
for(let e of g.nodes){let ob=e.observations.find(o=>o.frame_id===fid);if(!ob?.visible||!ob.box_xyxy)continue;let selected=e.entity_id===target;if(!selected&&!anchors.has(e.entity_id))continue;
let [x,y,x2,y2]=ob.box_xyxy;ctx.strokeStyle=selected?'#ff7518':'#32a9ff';ctx.lineWidth=selected?4:2;ctx.strokeRect(x,y,x2-x,y2-y);ctx.fillStyle=ctx.strokeStyle;ctx.font='15px sans-serif';ctx.fillText(e.entity_id,Math.max(0,x),Math.max(17,y-4));}};im.src=D.photos[g.shot_id+':'+fid]}
function show(row){current=row;let ev=D.run.solutions[solutionIndex]?.match_evidence.find(e=>e.source===row.source);$('detail').textContent=JSON.stringify({slot:row,evidence:ev||null},null,2);draw(0);draw(1);document.querySelectorAll('#rows tr').forEach(tr=>tr.classList.toggle('active',tr.dataset.slot===row.slot_id));}
function refresh(){solutionIndex=Number($('solution').value)||0;let sol=D.run.solutions[solutionIndex];activeRows=rowsForSolution(solutionIndex);$('rows').replaceChildren();for(let row of activeRows){let tr=document.createElement('tr');tr.dataset.slot=row.slot_id;for(let value of [row.slot_id,label(row.source),label(row.target),words[row.status]||row.status]){let td=document.createElement('td');td.textContent=value;tr.append(td)}tr.onclick=()=>show(row);$('rows').append(tr)}
$('transform').textContent=sol?` 匹配 ${sol.mapping.length} 对；归一目标 ${sol.normalized_objective.toFixed(4)}；yaw ${(sol.hypothesis.yaw*180/Math.PI).toFixed(1)}°；尺度 ${sol.hypothesis.scale.toFixed(3)}`:'未找到可靠骨架';
$('backbone').textContent=sol?JSON.stringify({anchors:sol.hypothesis.anchors.map(([i,j])=>[label(D.graphs[0].nodes[i].entity_id),label(D.graphs[1].nodes[j].entity_id)]),transform:sol.hypothesis,objective_trace:sol.objective_trace},null,2):'无';if(activeRows.length)show(activeRows[0]);}
D.graphs.forEach((g,k)=>{for(let fid of g.frames){let o=document.createElement('option');o.value=fid;o.textContent='frame '+fid;$('frame'+k).append(o)}$('frame'+k).onchange=()=>draw(k)});
D.run.solutions.forEach((r,k)=>{let o=document.createElement('option');o.value=k;o.textContent=`解 ${k+1}${r.within_pilot_cost_band?' · 在候选代价带内':''}`;$('solution').append(o)});$('solution').onchange=refresh;
$('summary').textContent=`实体 ${D.summary.entities.join(' / ')}；非空三维状态 ${D.summary.nonnull_states.join(' / ')}；候选 ${D.summary.candidate_pairs} 对；${JSON.stringify(D.summary.status_counts)}。共 ${D.run.solutions.length} 个保留解，${D.run.plausible_solution_count||0} 个位于预设代价带内。`;refresh();
</script></html>'''
    (root/'viewer.html').write_text(page.replace('__DATA__',data))
    (root/'display_images.json').write_text(json.dumps(photo_manifest,indent=2)+'\n')
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font=ImageFont.truetype(font_path,14);small=ImageFont.truetype(font_path,12);large=ImageFont.truetype(font_path,22)
    # All nodes covered in the selected best candidate map, including nulls.
    overview=Image.new('RGB',(1744,610),'#f3f6f9');dr=ImageDraw.Draw(overview)
    dr.text((20,12),'Geometry-only slot candidates | Shot1 / Shot3 | NOT verified identities',fill='#203344',font=large)
    for k,g in enumerate(graphs):
        fid=24 if 24 in g['frames'] else g['frames'][0]
        im=Image.open(frames_root/g['shot_id']/f'frame_{fid:06d}.jpg').convert('RGB')
        xoff=20+k*872;overview.paste(im,(xoff,80));dr.text((xoff,50),g['shot_id']+' / frame '+str(fid),fill='black',font=font)
        for row in slots:
            eid=row['source'] if k==0 else row['target']
            if eid is None:continue
            e=next(e for e in g['nodes'] if e['entity_id']==eid)
            ob=next(o for o in e['observations'] if o['frame_id']==fid)
            if not ob['visible'] or not ob['box_xyxy']:continue
            x,y,x2,y2=ob['box_xyxy'];color='#16bb9d' if row['status'].startswith('stable') else '#ff912a' if row['source'] and row['target'] else '#bd7cef'
            dr.rectangle((xoff+x,80+y,xoff+x2,80+y2),outline=color,width=2)
            text=row['slot_id'];bx=xoff+max(0,min(x,810));by=80+max(0,y-16)
            dr.rectangle((bx,by,bx+45,by+17),fill='#152535');dr.text((bx+1,by),text,fill=color,font=small)
    dr.text((20,575),'Green: stable in pilot checks | Orange: ambiguous candidate | Purple: unmatched | See viewer.html for evidence',fill='#263a4a',font=font)
    overview.save(root/'overview.png')
    # Clickable offline viewer is primary; this sheet is a compact all-slot fallback.
    sheet=Image.new('RGB',(1120,70+len(slots)*150),'#f3f6f9');draw=ImageDraw.Draw(sheet)
    draw.text((15,12),'All best-solution slots (geometry only; semantic identity unchecked)',font=large,fill='black')
    for idx,row in enumerate(slots):
        y=60+150*idx;draw.text((12,y),row['slot_id']+' | '+row['status'],font=font,fill='#21313f')
        for k,g in enumerate(graphs):
            eid=row['source'] if k==0 else row['target'];x=15+550*k
            if eid is None:draw.text((x,y+30),'UNMATCHED',font=large,fill='#8561a9');continue
            e=next(n for n in g['nodes'] if n['entity_id']==eid)
            observations=[o for o in e['observations'] if o['visible'] and o['box_xyxy']]
            draw.text((x,y+25),(eid+' '+e['name'])[:67],font=small,fill='black')
            if observations:
                ob=next((o for o in observations if o['frame_id']==24),observations[0])
                im=Image.open(frames_root/g['shot_id']/f'frame_{ob["frame_id"]:06d}.jpg').convert('RGB')
                x1,y1,x2,y2=ob['box_xyxy'];crop=im.crop((max(0,x1-6),max(0,y1-6),min(im.width,x2+6),min(im.height,y2+6)))
                crop.thumbnail((520,90));sheet.paste(crop,(x,y+45))
    sheet.save(root/'slots_contact_sheet.jpg',quality=90)
    lines=['# Shot1 / Shot3 关系槽位匹配：第一轮实际结果','',
           '仅几何结构候选；没有用名字、图像特征或 prompt 参与匹配，也没有人工改配对。',
           '','[交互查看结果](viewer.html) · [全部槽位图](slots_contact_sheet.jpg) · [原图概览](overview.png)',
           '',f'实体 {summary["entities"]}，非空 OBB {summary["nonnull_states"]}，候选对 {summary["candidate_pairs"]}。',
           f'最佳候选解匹配 {summary["best_matches"]} 对；状态统计：`{json.dumps(summary["status_counts"],ensure_ascii=False)}`。',
           '', '**这些不是身份准确率。** 稳定仅表示本次有限搜索及固定敏感性条件下没有改变；未匹配不证明删除/新增。',
           '', '| 槽位 | Shot1 | Shot3 | 状态 |','|---|---|---|---|']
    for row in slots:
        def label(x):return (x+' '+names[x]).replace('|','/') if x else '—'
        lines.append(f'| {row["slot_id"]} | {label(row["source"])} | {label(row["target"])} | {row["status"]} |')
    if run['solutions']:
        best=run['solutions'][0]
        lines+=['','## 最佳候选骨架','',*['- '+names[graphs[0]['nodes'][i]['entity_id']]+' ↔ '+names[graphs[1]['nodes'][j]['entity_id']] for i,j in best['hypothesis']['anchors']],
                '',f'目标值 {best["objective"]:.6f}；yaw {np.degrees(best["hypothesis"]["yaw"]):.3f}°；目标→源尺度 {best["hypothesis"]["scale"]:.6f}。这些是候选变换，不是已验证世界配准。']
    lines+=['','## 实现范围与限制','',
            '- 完成逐帧关系图、关系邻域描述、多三点骨架候选、局部分配和带成对代价的联合改进；允许两侧独立空匹配。',
            '- 源图距离中位数只作固定报告单位；目标通过单一正尺度和保重力 yaw 变换到源图，没有分别归一两侧以强行一致。',
            '- 当前骨架是三实体候选，在各假设下固定；多假设加局部搜索没有全局最优保证。',
            '- 六帧保留逐帧关系；中位数用于静态布局候选，时序变化大的实体不宣称获得动态身份关联。',
            '- 默认参数未校准；另运行 null 0.40/0.70、较紧几何容差、偶数/奇数采样帧五个固定条件。',
            '- 纯几何不能验证单支笔/笔组等语义粒度，也可能将不同类别对象匹配为结构角色；输出明确保留 scope_compatibility=not_semantically_verified。',
            '- 未做目标关系留出，不计算 S_RC；不能将优化过的关系残差解释为独立一致性评分。',
            '- 没有重跑检测、调用 VLM/Codex CLI 或使用 GPU。原图仅在求解完成后用于结果展示，并逐帧核对原始哈希。',
            '', '输入、运行时间、节点、代码哈希见 `summary.json`；完整候选和优化轨迹见 `matching.json`；逐帧关系见 `shot1_relations.json` 和 `shot3_relations.json`。']
    (root/'README.md').write_text('\n'.join(lines)+'\n')
    print('Viewer, overview, contact sheet and complete result table written.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--frames-root',required=True,type=Path)
    args=p.parse_args();render(args.run.resolve(),args.frames_root.resolve())
