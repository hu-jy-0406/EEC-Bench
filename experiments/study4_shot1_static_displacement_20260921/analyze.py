"""Small deterministic within-shot all-pair center-distance diagnostic; no inference."""
import csv,hashlib,itertools,json,math
from pathlib import Path
OUT=Path(__file__).resolve().parent
CASE=OUT.parents[0]/'within_negative_review_20260920/full/study4'
p=CASE/'selected/shot1_scene.json';raw=p.read_bytes();g=json.loads(raw)
names={'e1':'青花杯组','e2':'墙上装框画','e4':'木茶几','e5':'电视','e6':'木电视柜','e7':'电视柜上的盆栽','e8':'沙发','e9':'室外花盆','e10':'书架','e11':'壁炉台垂蔓植物','e12':'壁炉台小相框','e13':'室外开花植物','e14':'书架旁植物','e15':'壁炉台小花瓶','e16':'花纹靠垫','e17':'窗帘'}
entities=[];pairs=[];centers=[]
for e in g['entities']:
 if e['motion_status']!='static':continue
 obs=[];missing=[]
 for r in e['frame_evidence']:
  geom=r.get('geometry');c=geom.get('center_world') if geom else None
  if not r['visible'] or r['box_xyxy'] is None or c is None:
   missing.append(r['frame_id']);continue
  assert len(c)==3 and all(math.isfinite(x) for x in c)
  obs.append(dict(frame_id=r['frame_id'],center=c))
  centers.append(dict(entity_id=e['entity_id'],frame_id=r['frame_id'],x=c[0],y=c[1],z=c[2],box_xyxy=r['box_xyxy'],fusion_selected=r.get('selected'),geometry_reason=r.get('reason')))
 own=[dict(entity_id=e['entity_id'],frame_a=a['frame_id'],frame_b=b['frame_id'],distance=math.dist(a['center'],b['center'])) for a,b in itertools.combinations(obs,2)]
 n=len(obs);assert len(own)==n*(n-1)//2
 maximum=max(own,key=lambda x:x['distance']) if own else None
 row=dict(entity_id=e['entity_id'],name=e['name'],name_zh=names[e['entity_id'].split('/')[-1]],m=len(e['frame_evidence']),n=n,pair_count=len(own),mean_distance=math.fsum(r['distance'] for r in own)/len(own) if own else None,max_distance=maximum['distance'] if maximum else None,max_frame_pair=[maximum['frame_a'],maximum['frame_b']] if maximum else None,valid_frame_ids=[r['frame_id'] for r in obs],missing_frame_ids=missing)
 entities.append(row);pairs.extend(own)
entities.sort(key=lambda e:e['mean_distance'] if e['mean_distance'] is not None else -1,reverse=True)
result=dict(source_case=str(CASE),source_graph=str(p),source_sha256=hashlib.sha256(raw).hexdigest(),shot_id='shot1',frame_ids=[c['frame_id'] for c in g['cameras']],coordinate_system=g['coordinate_system'],units='Shot1 model coordinate units; not calibrated meters',formula='mean = sum_{i<j} ||c_i-c_j||_2 / C(n,2); max = max_{i<j} ||c_i-c_j||_2',population='Frozen whole-shot static labels; every visible original observation with box and finite center, regardless of fusion selection or residual',n_less_than_two='mean and max null, not zero',entities=entities,pairs=pairs,centers=centers,excluded_moving=[e['entity_id'] for e in g['entities'] if e['motion_status']!='static'],new_model_calls=0,tokens=0,api_usd=0)
assert hashlib.sha256(p.read_bytes()).hexdigest()==result['source_sha256']
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for name,rows in [('entities',entities),('pair_distances',pairs),('frame_centers',centers)]:
 with (OUT/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['# Study4 Shot1 静止实体帧间中心偏差','',
'原始帧编号：0、48、96、144、192、240。沿用冻结whole-shot static标签，女子moving排除。每帧只取现有原始3D框中心，不用融合框，不根据异常距离、fusion selected标记或质量事后剔除有效观测；缺框/缺几何不补点。',
'', '对n个有效中心枚举全部n(n−1)/2个无序不同帧组合；每对计算三维欧式距离，再取算术平均和最大值。n<2两项为null。单位是本镜头模型坐标单位，不是校准米；是位置变化测量，不自动等于真实移动或异常分数。',
'', '| 实体 | n/m | 距离对数 | 平均距离 | 最大距离 | 最大值帧对 |','|---|---:|---:|---:|---:|---|']
for e in entities:
 values=['—' if e[k] is None else f'{e[k]:.6f}' for k in ('mean_distance','max_distance')]
 lines.append(f'| {e["name_zh"]} ({e["entity_id"]}) | {e["n"]}/{e["m"]} | {e["pair_count"]} | {values[0]} | {values[1]} | {e["max_frame_pair"] or "—"} |')
lines+=['','青花杯组保持历史集合范围：其逐帧代表框是原始候选成员框，不保证为整个集合包围框，不能把集合代表中心变化直接解释为同一个杯子的运动。','',
'产物：entities.csv（实体汇总）、frame_centers.csv（逐帧坐标）、pair_distances.csv（每个帧对距离）、results.json（含来源hash）。未改生产评分/运动标签/检测/几何/注册；轻量JSON和math计算，无GPU，无模型调用，0tokens/USD0 API。']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
