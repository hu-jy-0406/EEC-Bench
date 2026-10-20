from pathlib import Path
import json,sys,itertools,hashlib
import numpy as np
P=Path(__file__).resolve().parent
r=json.loads((P/'results.json').read_text());case=Path(r['source_case']);reg=r['registration']
data=np.load(case/'pairs/pair_000/registration/roma_geometry/correspondences.npz')['data']
res=np.linalg.norm(reg['scale']*(data[:,10:13]@np.asarray(reg['rotation']).T)+reg['translation']-data[:,7:10],axis=1)
mask=(data[:,0]==120)&(data[:,1]==0)
def stat(v):return dict(n=len(v),median=float(np.median(v)),p90=float(np.percentile(v,90)),max=float(np.max(v))) if len(v) else None
endpoint=dict(all=stat(res[mask]),by_group={str(int(g)):stat(res[mask&(data[:,2]==g)]) for g in np.unique(data[mask,2])})
assert abs(np.median(res)-reg['full_pool_residual']['median'])<1e-10
lamp=next(e for e in r['entities'] if e['group_id']=='g03')
g=json.loads((case/'selected/shot1_scene.json').read_text());e=next(e for e in g['entities'] if e['entity_id']=='shot1/e3')
selected=[f for f in e['frame_evidence'] if f.get('selected') and f.get('geometry') and f['visible']]
ds=[np.linalg.norm(np.asarray(a['geometry']['center_world'])-b['geometry']['center_world']) for a,b in itertools.combinations(selected,2)]
sensitivity=dict(existing_selected_frames=[f['frame_id'] for f in selected],pairwise=stat(np.asarray(ds)),p95=float(np.percentile(ds,95)))
a,b=(np.asarray(lamp[k]) for k in ('center_shot1','center_shot3_aligned'))
a[2]-=lamp['size_shot1'][2]/2;b[2]-=lamp['size_shot3_aligned'][2]/2
extra=dict(endpoint_point_residual=endpoint,lamp_existing_quality_flag_sensitivity=sensitivity,lamp_lower_face_center_distance=float(np.linalg.norm(b-a)),
 note='Lower OBB face center is a diagnostic support-position proxy, not a tracked physical landmark. No data removed from registration or production scores.')
(P/'additional_diagnostics.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2)+'\n')
cn={'g02':'水杯','g03':'台灯','g04':'女子','g05':'书桌','g07':'笔筒','g09':'窗边植物','g13':'木椅','g14':'暖气片','g16':'窗边花盆','g17':'笔集合'}
lines=['# Study3 统一坐标位移与噪声诊断','',
'结论：水杯和笔筒的几何位移明显突出，可以作为强候选；台灯的小幅水平位移无法凭当前注册/框中心数据可靠地区分于误差。这里是测量显著程度的诊断，不是独立真值或统计显著性检验。',
'', '## 范围和定义','',
'读取 pipeline_parallel_20260921/run，沿用既有 FPS32 注册、匹配与原始逐帧框；Shot1第120帧，对比Shot3第0帧，Shot3经 sR Q+t 转至Shot1系。10个confirmed匹配，9个端点具备几何；女子缺端点，不替补。其他未匹配/模糊实体不能生成同一实体位移。未拟合新变换、未删注册点、未修改任何生产阈值/评分。单位为Shot1模型坐标单位，不是校准米。',
'',
'中心距离为 ||c3_aligned-c1||。框间距离是两个实体OBB实体体积间最短距离，凸有界最小二乘求解；0表示相交/重叠，不表示没有位移。镜头内波动为同一实体全部可用帧中心两两距离的P95，取两个镜头较大值；这些帧对相互依赖，只是描述性误差/变化代理，包含遮挡、框范围变化和可能真实漂移，不能当作纯噪声标准差。',
'', '| 实体 | 中心距离 | 水平距离 | 框间最短距离 | 镜头内波动P95 | 位移/P95 |','|---|---:|---:|---:|---:|---:|']
for x in r['entities']:
 if x['center_distance'] is None:lines.append('| 女子 | 不可算 | — | — | — | — |');continue
 lines.append('| '+cn[x['group_id']]+' | '+' | '.join(f'{x[k]:.4f}' for k in ['center_distance','horizontal_distance','solid_obb_gap','within_p95_max','displacement_over_within_p95'])+' |')
lines+=['','## 台灯为什么不能直接认定位置异常','',
'端点中心 Shot1=(0.890296,0.074935,0.288724)，对齐Shot3=(0.914245,0.044439,0.165696)，差=(+0.023949,-0.030496,-0.123028)。中心距离0.128994左右，其中水平仅0.038773左右，主要是垂直偏移。',
'',
'框尺寸由(0.343491,0.305751,0.439421)变为(0.161305,0.144849,0.274622)。尺寸/可见范围变化、真实形状变化和重建误差都会改变中心，不能把中心差全当物体平移。下表面中心代理距离为 %.6f，亦不能作为真实灯座跟踪。'%extra['lamp_lower_face_center_distance'],
'',
'全量Shot1帧间P95=0.595228主要受第96帧影响：框仅覆盖约57%%可见范围，projection IoU=0.337，原几何记录已经标注robust_center_outlier（fusion selected=false）。其他帧未删除；全量诊断保持原状。作为敏感性描述，沿用已有selected标记的帧%s，其两两距离P95=%.6f。Shot3全量P95=0.018934。即使不让单帧异常主导，良好帧内重复性也不能代表跨视角准确度。'%(sensitivity['existing_selected_frames'],sensitivity['p95']),
'', '## 跨镜头误差比帧内抖动更关键','',
'保留的结构参照书桌端点残差0.0977，暖气片0.5375。窗边植物0.4484、花盆0.5485与暖气片在Y方向呈相近偏移（约-0.44至-0.55），提示局部系统误差/场景几何不一致的可能性；不能把这些未经独立真值确认的差异全部称为噪声。暖气片位移/帧内P95约5.32，也说明“超过帧内抖动几倍”不足以证实真实移动。',
'',
'固定注册全候选池4852点：median=%.6f，P90=%.6f；FPS32实际拟合点median=%.6f，P90=%.6f。均含匹配/深度/场景变化等误差；拟合点及历史holdout划分不是独立验证集。'%(reg['full_pool_residual']['median'],reg['full_pool_residual']['p90'],reg['selected_residual']['median'],reg['selected_residual']['p90']),
'', '仅120→0端点对应点（同一个固定变换，未重拟合）：','', '| 锚组 | 点数 | 残差中位数 | P90 |','|---|---:|---:|---:|']
for k,v in endpoint['by_group'].items():lines.append(f'| {k} | {v["n"]} | {v["median"]:.4f} | {v["p90"]:.4f} |')
lines+=['','## 对位移候选筛选的含义','',
'水杯1.3826、笔筒1.0842明显高于自身帧内波动，并在全部跨镜头帧组合中维持相近偏移：跨组合距离中位数分别1.3892和1.0482。相对桌心的关系变化量仍为1.3197、1.0255，说明不只是全场共同平移。它们足以作为值得审核的强候选，但仅凭本例不能确定通用阈值或误报率。',
'',
'笔集合0.8161也较大，但细小物/集合代表框范围不稳定，不能视作与水杯同等可靠的物理位移。台灯0.1290与局部注册/尺寸误差混杂，水平0.0388更弱；单一绝对距离阈值难以同时检出台灯又避免将背景参照物误报。若后续设计距离候选，应同时保留原始位移、框尺寸/可见范围、帧内波动以及空间邻近参照的跨视角残差，不把帧内低抖动当成跨视角低误差。本次不采用新规则。',
'', '![距离与帧内波动](displacement_vs_spread.png)','',
'产物：results.json含所有统一坐标、框尺寸、距离、逐帧中心与原文件hash；entities.csv；additional_diagnostics.json；PNG/PDF图。来源hash核验及OBB距离解析例自检通过。只在既有196093/node197低负载CPU执行；0模型调用、0tokens、USD0 API，不使用GPU。']
(P/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(extra,ensure_ascii=False,indent=2))
