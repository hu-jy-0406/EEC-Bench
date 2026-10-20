"""Evaluate frozen registration variants on every confirmed common entity."""
import csv, hashlib, json, sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
BASE=Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench')
ROOT=BASE/'experiments/registration_methods_20260919'
OUT=ROOT/'common_entity_evaluation';OUT.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,d:p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
CASES={'study2':BASE/'experiments/study2_integrated_full_fresh_20260919/study2','study3':BASE/'experiments/study3/run_cpu02'}
rows=[];details=[];coverage={};hashes={}
for name,case in CASES.items():
 files=[case/'matching.json',*[case/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']],ROOT/name/'anchors.json',ROOT/'comparison.json']
 hashes.update({str(p):sha(p) for p in files})
 look={e['entity_id']:e for s in ['shot1','shot3'] for e in read(case/'selected'/f'{s}_scene.json')['entities']}
 groups=read(case/'matching.json')['groups'];anchors=read(ROOT/name/'anchors.json');anchor_pairs={(tuple(g['a_ids']),tuple(g['b_ids'])) for g in anchors}
 common=[];excluded=[]
 for g in groups:
  if g['identity']!='matched':
   if g['a_ids'] and g['b_ids']:excluded.append(dict(group_id=g['group_id'],reason=g['identity']))
   continue
  if len(g['a_ids'])!=1 or len(g['b_ids'])!=1:raise ValueError('Explicit many-to-many evaluation required')
  a,b=[look[g[k][0]] for k in ['a_ids','b_ids']]
  if a['geometry'] is None or b['geometry'] is None:
   excluded.append(dict(group_id=g['group_id'],reason='missing_geometry'));continue
  common.append(dict(group_id=g['group_id'],a_ids=g['a_ids'],b_ids=g['b_ids'],names=[a['name'],b['name']],motion=[a['motion_status'],b['motion_status']],static=a['motion_status']==b['motion_status']=='static',anchor=(tuple(g['a_ids']),tuple(g['b_ids'])) in anchor_pairs,target=a['geometry'],source=b['geometry']))
 mapped={i for g in groups for k in ['a_ids','b_ids'] for i in g[k]}
 coverage[name]=dict(evaluated=len(common),static=sum(g['static'] for g in common),nonstatic=sum(not g['static'] for g in common),excluded=excluded,entities_missing_from_historical_identity=[dict(entity_id=i,name=e['name'],motion=e['motion_status']) for i,e in look.items() if i not in mapped],groups=[{k:v for k,v in g.items() if k not in ['target','source']} for g in common])
 for r in read(ROOT/'comparison.json'):
  if r['case']!=name:continue
  s=r['scale'];th=np.radians(r['yaw_deg']);c,d=np.cos(th),np.sin(th);rot=np.array([[c,-d,0],[d,c,0],[0,0,1]]);t=np.array(r['translation']);per=[]
  for g in common:
   p=np.array(g['target']['corners_world']);q=np.array(g['source']['corners_world']);assert p.shape==q.shape==(8,3)
   tq=s*q@rot.T+t;cost=np.linalg.norm(p[:,None,:]-tq[None,:,:],axis=2);ia,ib=linear_sum_assignment(cost)
   center=float(np.linalg.norm(s*rot@np.array(g['source']['center_world'])+t-g['target']['center_world']))
   assert len(set(ia))==len(set(ib))==8
   per.append(dict(group_id=g['group_id'],names=g['names'],static=g['static'],anchor=g['anchor'],center_distance=center,corner_mean=float(cost[ia,ib].mean()),corner_sum=float(cost[ia,ib].sum()),source_corner_indices=ib.tolist(),target_corner_indices=ia.tolist()))
  for subset,items in [('all_confirmed_common',per),('static_common',[g for g in per if g['static']]),('nonstatic_common',[g for g in per if not g['static']]),('static_nonanchor',[g for g in per if g['static'] and not g['anchor']])]:
   rows.append(dict(case=name,method=r['method'],population=subset,entities=len(items),center_mean=float(np.mean([g['center_distance'] for g in items])) if items else None,corner_mean=float(np.mean([g['corner_mean'] for g in items])) if items else None))
  static=next(v for v in rows if v['case']==name and v['method']==r['method'] and v['population']=='static_common')
  assert abs(static['corner_mean']-r['reviewed_static_box_corner_mean'])<1e-10
  assert abs(static['center_mean']-r['reviewed_static_center_mean'])<1e-10
  details.append(dict(case=name,method=r['method'],entities=per))
for p,h in hashes.items():assert sha(Path(p))==h
save(OUT/'comparison.json',rows);save(OUT/'entity_details.json',details);save(OUT/'coverage.json',coverage);save(OUT/'input_hashes.json',hashes)
with (OUT/'comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
order=['baseline_all','m1_top_confidence_32','m1_top_confidence_64','m1_top_confidence_128','m1_fps_32','m1_fps_64','m1_fps_128','m1_confidence_fps_32','m1_confidence_fps_64','m1_confidence_fps_128','m2_direct','m3_corners','m4_hybrid']
lines=['# 共现实体上的冻结配准评估','','所有方法使用同一份历史最终身份匹配；不重跑匹配或拟合。每个实体等权。中心误差为三维欧氏距离；角点误差为每个box内部8角点最小距离一一对应的平均值，再跨实体平均。仅重算评价时角点对应，不修改配准参数。单位是各自Shot1模型单位，不是米。','','此前全RoMa池只包含anchor区域的有效点。这里评估所有identity=matched且两侧有几何的实体；ambiguous/scope_mismatch不强行当同一实体。静止非anchor子集按初始拟合anchor列表排除。','','Study2历史matching仅覆盖静止实体：8对确认共现实体，3个运动实体局部记录未进入身份匹配（包括两shot人物和Shot1红书）；所以不能把这8对称作包含运动实体的完整共现集合。Study3包含全部运动状态：10对=9静止+1运动人物，均有3D几何。运动人物的误差包含实际位置/姿态变化，不是纯配准误差。','','历史身份复核曾使用旧配准，其对应不是独立真值；所有方法冻结同一对应以避免各自挑选有利实体。未拟合于这些box也不等于严格独立真值测试；几何重建、box大小/朝向和真实场景变化都会影响误差。']
for pop in ['all_confirmed_common','static_common','static_nonanchor','nonstatic_common']:
 lines += ['',f'## {pop}','','|方法|Study2实体数|Study2中心|Study2角点|Study3实体数|Study3中心|Study3角点|','|---|---:|---:|---:|---:|---:|---:|']
 for m in order:
  vals=[]
  for case in CASES:
   r=next(r for r in rows if r['case']==case and r['method']==m and r['population']==pop)
   vals.extend([str(r['entities']),*[f'{r[k]:.4f}' if r[k] is not None else '—' for k in ['center_mean','corner_mean']]])
  lines.append('|'+m+'|'+'|'.join(vals)+'|')
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
save(OUT/'audit.json',dict(passed=True,input_hashes_unchanged=True,static_metrics_reproduce_previous_results=True,corner_bijections_verified=True,methods_per_case=13,new_model_calls=0,new_model_tokens=0,refitted=False))
print((OUT/'REPORT.md').read_text())
