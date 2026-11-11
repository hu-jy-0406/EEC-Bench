#!/usr/bin/env python3
"""Render comparison evidence with frame-selectable original-image overlays."""
import argparse
import base64
import json
from pathlib import Path


def render(root):
    read=lambda p:json.loads(p.read_text())
    result=read(root/"comparison.json")
    graphs=[read(root/("graph_"+sid)/"graph.json") for sid in result["source_shots"]]
    manifest=read(root/"manifest.json")
    photos={f["shot_id"]+":"+str(f["frame_id"]):"data:image/jpeg;base64,"+
        base64.b64encode(Path(f["path"]).read_bytes()).decode() for f in manifest["images"]}
    data=json.dumps(dict(result=result,graphs=graphs,photos=photos),ensure_ascii=False).replace("</","<\\/")
    html="""<!doctype html><html lang="zh"><meta charset="utf-8"><title>场景图比较与证据</title>
<style>body{font:15px system-ui;margin:22px;background:#f3f5f8;color:#172536}h1{font-size:24px}
button,select{padding:8px;margin:4px}.layout{display:grid;grid-template-columns:340px 1fr;gap:20px}
#list{max-height:80vh;overflow:auto}.item{padding:12px;margin:6px;background:white;border-left:5px solid #aaa;cursor:pointer}
.conflict{border-color:#ce4747}.compatible{border-color:#27946b}.undetermined{border-color:#d2a030}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px}
.views{display:grid;grid-template-columns:1fr 1fr;gap:12px}canvas{width:100%;background:white}.caption{min-height:40px}
small{color:#596578}.panel{background:white;padding:10px}
@media(max-width:900px){.layout,.views{grid-template-columns:1fr}#list{max-height:35vh}}
</style><h1>同场景局部图：互补、冲突与未决</h1>
<p>颜色表示自动规则分类；框标出取证区域。视觉证据仍需核验，未决不计为已确认一致。</p>
<p><a href="README.md">结果表</a> · <a href="comparison.json">比较 JSON</a> · <a href="scene_memory.json">融合内存</a></p>
<div id="summary"></div><select id="filter"><option value="">全部</option><option value="conflict">冲突</option>
<option value="compatible">相容 / 互补 / 合法变化</option><option value="undetermined">未决 / 提取缺口</option></select>
<div class="layout"><div id="list"></div><main><h2 id="title"></h2><div class="views">
<div class="panel"><div id="name0"></div><select id="frame0"></select><canvas id="canvas0"></canvas><p class="caption" id="caption0"></p></div>
<div class="panel"><div id="name1"></div><select id="frame1"></select><canvas id="canvas1"></canvas><p class="caption" id="caption1"></p></div>
</div><details open><summary>结构化证据、门控与判定规则</summary><pre id="detail"></pre></details></main></div>
<script>
const D=__DATA__,groups=new Map(D.result.inventory_diff.map(g=>[g.group_id,g]));
const words={presence_conflict:'存在 / 占位冲突',relation_conflict:'空间关系冲突',shared_identity:'身份对应',
shared_relation:'共同关系',compatible_partial:'部分约束相容',complementary_view:'互补视野',explained_change:'允许的变化',
observation_gap:'图中漏记 / 提取缺口',visibility_unresolved:'可见性未决',relation_unresolved:'关系证据不足',
extraction_evidence_conflict:'两阶段取证分歧',within_shot_change:'镜头内状态改变',
ambiguous:'身份待定',scope_mismatch:'实体粒度不同',unmatched_endpoint_or_anchor:'端点 / 参考轴未对齐'};
const $=id=>document.getElementById(id);let current=null;
function groupName(id){const g=groups.get(id);if(!g)return id;
return D.graphs.flatMap((graph,idx)=>g[(idx===0?'a':'b')+'_ids'].map(e=>graph.entities.find(x=>x.entity_id===e)?.name||e)).join(' / ');}
function label(item){return item.group_ids.map(groupName).join('；')||item.item_id;}
function evidenceFor(item,sid){
const e=item.evidence||{};if(item.kind==='presence'){
if(sid===item.source_shot)return e.source_evidence||[];
return (e.frames||[]).map(f=>({frame_id:f.frame_id,region_xyxy:f.expected_region_xyxy,reason:f.observation+'：'+f.reason}));}
return e[sid===D.graphs[0].shot_id?'evidence_a':'evidence_b']||[];
}
function draw(idx){const graph=D.graphs[idx],fid=Number($('frame'+idx).value),rows=evidenceFor(current,graph.shot_id);
const row=rows.find(e=>e.frame_id===fid),canvas=$('canvas'+idx),ctx=canvas.getContext('2d'),im=new Image();
const requested=current.item_id;
im.onload=()=>{if(current.item_id!==requested||Number($('frame'+idx).value)!==fid)return;
canvas.width=im.width;canvas.height=im.height;ctx.drawImage(im,0,0);
if(row?.region_xyxy){const [x1,y1,x2,y2]=row.region_xyxy;ctx.strokeStyle='#ff7630';ctx.lineWidth=3;ctx.strokeRect(x1,y1,x2-x1,y2-y1);}
$('caption'+idx).textContent=row?.reason||'此帧没有该项专属证据；仅显示原图供检查。';};
im.src=D.photos[graph.shot_id+':'+fid];
}
function show(item){current=item;$('title').textContent=(words[item.reason_code]||item.reason_code)+' — '+label(item);
$('detail').textContent=JSON.stringify(item,null,2);
D.graphs.forEach((g,idx)=>{const select=$('frame'+idx);select.replaceChildren();$('name'+idx).textContent=g.shot_id;
for(const f of g.frames){const option=document.createElement('option');option.value=f.frame_id;option.textContent='frame '+f.frame_id;select.append(option);}
const ev=evidenceFor(item,g.shot_id);let fid=ev[0]?.frame_id;
if(item.kind==='presence'&&g.shot_id===item.target_shot&&item.decisive_target_frames.length)fid=item.decisive_target_frames[0];
if(fid!==undefined)select.value=fid;select.onchange=()=>draw(idx);draw(idx);});}
function listing(){$('list').replaceChildren();for(const item of D.result.items){if($('filter').value&&item.assessment!==$('filter').value)continue;
const div=document.createElement('div');div.className='item '+item.assessment;const title=document.createElement('strong');
title.textContent=words[item.reason_code]||item.reason_code;const name=document.createElement('div');name.textContent=label(item);
div.append(title,name);div.onclick=()=>show(item);$('list').append(div);}}
$('summary').textContent='实体 '+D.graphs.map(g=>g.entities.length).join(' / ')+'；存在性查询 '+D.result.coverage.presence_queries+
'；关系查询 '+D.result.coverage.relation_queries+'；未对齐关系 '+D.result.coverage.unaligned_relation_claims;
$('filter').onchange=listing;listing();if(D.result.items.length)show(D.result.items[0]);
</script></html>"""
    (root/"viewer.html").write_text(html.replace("__DATA__",data))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);render(p.parse_args().run.resolve())
