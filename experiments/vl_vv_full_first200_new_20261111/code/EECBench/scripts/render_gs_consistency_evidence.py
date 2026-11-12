#!/usr/bin/env python3
"""Offline original-frame witness viewer; no model calls or image modification."""
import argparse,base64,hashlib,json
from pathlib import Path
from run_isolated_shot_static_3d import owned_compute_job

def render(root):
    owned_compute_job();read=lambda n:json.loads((root/n).read_text());manifest=read('manifest.json');images={}
    for row in manifest['sources'][2:]:
        source=json.loads(Path(row['path']).read_text())['shots'][0]
        for f in source['calibration']['images']:
            raw=Path(f['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Original image changed')
            images[source['shot_id']+'/'+str(f['frame_id'])]='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
    data=dict(frame_meta=read('payload.json')['images'],score=read('score.json'),graphs=[read('graph_a.json'),read('graph_b.json')],images=images,diagnostics=read('geometry_diagnostics.json'))
    encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gs 一致性评分与原帧证据</title>
<style>body{margin:24px auto;max-width:1450px;padding:0 20px;background:#f5f7fa;color:#172333;font:16px system-ui}h1{font-size:27px}.bar,.box{background:white;padding:18px;border-radius:10px;margin:12px 0}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}svg{display:block;width:100%;height:auto;background:#ddd}select{padding:8px;font:inherit;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}p{line-height:1.5}.muted{color:#596779}.tag{font-weight:bold}.conflict{color:#ba2525}.unknown{color:#697483}.compatible{color:#167397}.complement{color:#287b48}@media(max-width:850px){.cols{grid-template-columns:1fr}}</style>
<h1>Gs 跨 shot 一致性评分</h1><div id="summary" class="bar"></div><div class="bar"><label>实体比较单位：<select id="choose"></select></label><p class="muted">分数由固定规则计算。互补不扣分、不扩充分母；证据不足不算已知一致。下面显示原始帧与审核所引用的区域；矩形是审核证据范围，不是新检测结果。</p></div><div id="detail"></div>
<script id="data" type="application/json">DATA</script><script>
const D=JSON.parse(document.getElementById('data').textContent),S=D.score;
const labels={compatible:'有证据相容',conflict:'确认冲突',complement:'视角互补',unknown:'证据不足'};
const names={};for(const g of D.graphs)for(const e of g.entities)names[e.entity_id]=e.name;
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
const sum=document.getElementById('summary');sum.append(node('h2','WSC（上界） '+(S.score===null?'不可判定':S.score.toFixed(2)+' / 100')+' · 可判定覆盖率 '+(S.coverage===null?'不可判定':(100*S.coverage).toFixed(1)+'%')));
sum.append(node('p','相容 '+S.weights.compatible+'，冲突 '+S.weights.conflict+'，互补 '+S.weights.complement+'，证据不足 '+S.weights.unknown+'。未知项敏感性区间：'+JSON.stringify(S.identification_interval)+'（不是统计置信区间）。'));
sum.append(node('p','以冻结 Gs 的实体、空间框和支持数据为基础，结合原帧验证。几何配准 trusted='+D.diagnostics.trusted+'；审核同意不等于真值；有分歧时最多一次候选证据回查。','muted'));
const select=document.getElementById('choose');for(const g of S.groups){const o=node('option',labels[g.verdict]+' — '+[...g.a_ids,...g.b_ids].map(x=>names[x]).join(' / '));o.value=g.group_id;select.append(o)}
function svgWitness(w){const ns='http://www.w3.org/2000/svg',s=document.createElementNS(ns,'svg');const wh=D.frame_meta.find(f=>f.shot_id===w.shot_id&&f.frame_id===w.frame_id).image_size;s.setAttribute('viewBox','0 0 '+wh[0]+' '+wh[1]);const im=document.createElementNS(ns,'image');im.setAttribute('href',D.images[w.shot_id+'/'+w.frame_id]);im.setAttribute('width',wh[0]);im.setAttribute('height',wh[1]);s.append(im);const [x,y,x2,y2]=w.region_xyxy,r=document.createElementNS(ns,'rect');for(const [k,v]of Object.entries({x,y,width:x2-x,height:y2-y,fill:'none',stroke:'#ff304f','stroke-width':3}))r.setAttribute(k,v);s.append(r);return s}
function show(){const g=S.groups.find(x=>x.group_id===select.value),dest=document.getElementById('detail');dest.replaceChildren();const info=node('div',undefined,'box');info.append(node('h2',g.group_id+' · '+labels[g.verdict],g.verdict));info.append(node('p','权重 '+g.weight+'；计分门控：'+g.reason));const gd=node('details');gd.append(node('summary','查看 Gs 三维输入、支持度与门控结果'));const ents=D.graphs.flatMap(x=>x.entities).filter(x=>[...g.a_ids,...g.b_ids].includes(x.entity_id)).map(x=>({entity_id:x.entity_id,name:x.name,geometry:x.geometry,reliability:x.reliability,center_dispersion_relative:x.center_dispersion_relative}));gd.append(node('pre',JSON.stringify({entities:ents,gates:g.gate_results},null,2)));info.append(gd);dest.append(info);
for(let i=0;i<g.reviews.length;i++){const review=g.reviews[i],block=node('section',undefined,'box');block.append(node('h3',(['取证审核','独立复核','有界证据回查'][i])+'：'+labels[review.verdict]));block.append(node('p',review.reason));block.append(node('p','Gs 依据：'+review.gs_evidence));block.append(node('p','反事实位置：'+review.affected_location));block.append(node('p','反事实检验：'+review.counterfactual_test));block.append(node('p','替代解释：'+review.alternative_explanations,'muted'));const cols=node('div',undefined,'cols');for(const shot of S.shots){const col=node('div');col.append(node('h3',shot));for(const w of review.visual_evidence.filter(x=>x.shot_id===shot)){col.append(node('p','Frame '+w.frame_id+' · '+JSON.stringify(w.region_xyxy)));col.append(svgWitness(w));col.append(node('p',w.observation))}cols.append(col)}block.append(cols);dest.append(block)}}
select.onchange=show;select.value=(S.groups.find(g=>g.verdict==='conflict')||S.groups[0]).group_id;show();
</script></html>'''.replace('DATA',encoded)
    (root/'evidence.html').write_text(page);print(json.dumps(dict(path=str(root/'evidence.html'),original_images=len(images),groups=len(data['score']['groups']),offline=True,browser_tested=False)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);render(p.parse_args().run.resolve())
