import os,json,hashlib,itertools
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/eec-identityfree-final')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
H=Path(__file__).resolve().parent;RUN=H/'run01';OLD=H.parents[1]/'experiments/study012_two_scores_20260916/study2'
def read(p):return json.loads(p.read_text())
res=read(RUN/'comparison.json');new=read(RUN/'aligned_entities.json');old=read(OLD/'aligned_entities.json');fits=[old,new];colors={'shot1':'#1769ba','shot3':'#df6b17'}
ids={'shot1/e5':'Desk','shot3/e7':'Desk','shot1/e11':'Rug','shot3/e15':'Rug','shot1/e14':'Radiator','shot3/e18':'Radiator','shot1/e13':'Chair','shot3/e6':'Chair'}
points=np.concatenate([np.array(e['geometry']['corners_world']) for data in fits for sh in data['shots'] for e in sh['entities'] if e['entity_id'] in ids]);lo=points.min(0);hi=points.max(0);lo-=.25;hi+=.25
edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
fig,axes=plt.subplots(1,2,figsize=(13.5,7.2))
for col,(ax,data,title) in enumerate(zip(axes,fits,['Original: identity-filtered','New: no identity / entity masks'])):
 for sh in data['shots']:
  sid=sh['shot_id'];color=colors[sid]
  for e in sh['entities']:
   if e['entity_id'] not in ids:continue
   c=np.array(e['geometry']['corners_world']);label=ids[e['entity_id']]
   for i,j in edges:ax.plot(*c[[i,j],:2].T,color=color,lw=1.1 if label=='Rug' else 2,ls='--' if label=='Rug' else '-',alpha=.6 if label=='Rug' else .9)
   p=np.array(e['geometry']['center_world']);ax.scatter(*p[:2],color=color,s=24)
   offset=(5,7 if sid=='shot1' else -16)
   if label=='Rug':offset=(-38,7 if sid=='shot1' else -16)
   ax.annotate('S'+sid[-1]+' '+label,p[:2],xytext=offset,textcoords='offset points',color=color,fontsize=9,bbox=dict(fc='white',ec='none',alpha=.8,pad=1))
 ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_aspect('equal');ax.set_xlabel('X (Shot1 scene)');ax.set_ylabel('Y (Shot1 scene)');ax.grid(alpha=.15);ax.set_title(title,fontsize=14,weight='bold')
fig.suptitle('Study2 | main furniture in the same coordinate system',fontsize=17,weight='bold',y=.98)
fig.legend(handles=[Line2D([0],[0],color=c,lw=3,label=s.replace('shot','Shot ')) for s,c in colors.items()],loc='upper center',bbox_to_anchor=(.5,.94),ncol=2,frameon=False)
fig.text(.5,.025,'Top view with identical axis ranges. Dashed outlines: rug. Furniture selected only for display after fitting.',ha='center',fontsize=10)
fig.subplots_adjust(left=.06,right=.98,top=.85,bottom=.1,wspace=.17);fig.savefig(RUN/'main_furniture_comparison.png',dpi=160);fig.savefig(RUN/'main_furniture_comparison.jpg',dpi=120,pil_kwargs={'quality':90});plt.close(fig)
reg=read(RUN/'roma_geometry/registration.json');prep=read(RUN/'preparation_audit.json');schema=read(RUN/'roma_geometry/schema.json')
lines=['# Study2：不依赖跨shot实体身份的 RoMaV2 配准实验','','## 结论','','数值变换可以求解；本次全场景对齐仍不可靠。不能据负cosine数量降低认定真实一致性改善。新解更多拟合窗边窄带区域，书桌/地毯的旧结构留出匹配误差更大。','', '## 实际执行','','1. 复用同一次实验36组6×6原JPEG的RoMaV2 precise全图原始匹配，每组5000点。原始model.match/sample没有实体身份输入，原匹配文件哈希全部保存并复核。','2. 移除同身份结构区域限制、所有实体框/类别/动静遮罩；置信度>=0.2、双向匹配一致性<=3px；使用原Pi3X单shot深度/相机位姿提升到各自固定Z-up场景，深度置信度>=该帧第10百分位。','3. 180000原匹配留下23308点；固定48像素网格划分训练15216、留出8092。与旧流程相同划分谓词；同一重复纹理和临近帧仍可能相关，留出不是独立真实对应验证。','4. 保持旧优化模型：Shot3→Shot1，正尺度+重力约束偏航角+三维平移（5自由度）；1600组三点随机种子，候选按网格均衡的5px内点比例及截断误差排序，前8个做soft-L1对称重投影优化。去掉实体组均衡，组号恒为1，保留帧对/空间网格均衡。','5. 偶数/奇数帧分别500种子作诊断，不以其结果替换主解。主解冻结后才读取旧身份表、实体框、旧变换，用于输出与对照，不反馈拟合。','6. 在相同8092全图留出点和相同1343旧结构留出点上分别比较新旧解，另生成所有38个静态框以及主家具叠加图。','', 'RoMaV2本身提供2D对应；本实验仍需要原单shot Pi3X深度和相机位姿才能估计两个已有3D场景之间的尺度及平移。无需跨shot实体身份不等于无需单shot几何。','', '## 变换','', '| 参数 | 旧版 | 无身份新版 |','|---|---:|---:|',f"| yaw (deg) | {res['old_transform']['yaw_deg']:.6f} | {res['new_transform']['yaw_deg']:.6f} |",f"| scale | {res['old_transform']['scale']:.6f} | {res['new_transform']['scale']:.6f} |",f"| translation | {res['old_transform']['translation']} | {res['new_transform']['translation']} |",'', '## 同一评测点集比较','', '| 指标 | 旧版 | 新版 |','|---|---:|---:|']
m=res['same_population_metrics']
for field,label in [('median_pixels','全图留出中位误差(px)'),('p90_pixels','全图留出P90误差(px)'),('inlier_5px','全图留出<=5px比例')]:lines.append(f"| {label} | {m['old']['full_image_holdout'][field]:.6f} | {m['identity_free']['full_image_holdout'][field]:.6f} |")
for g,name in [('4','旧书桌区域，305点'),('10','旧地毯区域，7点'),('12','旧暖气片区域，1031点')]:lines.append(f"| {name}中位误差(px) | {m['old']['original_structure_groups'][g]['median_pixels']:.3f} | {m['identity_free']['original_structure_groups'][g]['median_pixels']:.3f} |")
lines+=['','旧结构集合中的对应也不是人工验证的真值，仅作为同一数据上的诊断，不把这些误差当绝对定位精度。新版未使用其标签参与求解。','', '## 输出与限制','','- main_furniture_comparison.png/jpg：主家具俯视对照','- overlay_comparison.png/jpg：全部静态框3D与俯视对照','- interactive.html：新版38个静态框的可旋转3D图','- match_support.jpg：同一帧对的内点分布；新解支持点主要在窗边窄带，覆盖不足','- comparison.json / pair_cosines_comparison.csv：全部数值与旧身份下55对cosine，仅诊断','',f"旧身份不变时负cosine数31→{res['negative_counts']['identity_free']}，但g16误配及g17/g01待核实未修复，也没有重做冲突复核或评分，不能把数量下降解释成检测变好。",'']
for rid in ['pair_g02_g06','pair_g01_g07','pair_g04_g10']:
 r=next(r for r in res['pair_cosines'] if r['relation_id']==rid);lines.append(f"- {rid}: {r['old_cosine']:.6f} → {r['identity_free_cosine']:.6f}")
lines+=['','## 验证与消耗','','变换解析恢复/正逆变换合成测试通过；拟合进程对matching.json、aligned_entities.json、spatial.json等文件访问主动报错。相机快照只含单shot相机和图像元数据，不含实体。提升及拟合不使用单shot实体字段。原JPEG、单shot几何、36匹配文件哈希未改变；旧55cosine和新留出误差复算通过。',f"复用既有GPU模型输出；新增模型调用0、模型token0、GPU任务0。使用已检查低负载的自有Slurm189667/node296，CPU2核。点提升耗时{prep['seconds']:.2f}s，三次拟合合计{reg['seconds']:.2f}s；不含排队、绘图及本轮交互。",'', '模型匹配中的重复纹理/动态像素、场景非刚性变化及单目几何误差仍会影响拟合；本实验仅测试去掉实体身份依赖，尚未解决这些问题。']
(RUN/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('REPORT COMPLETE', 'prepare seconds',prep['seconds'],'fit seconds',reg['seconds'])
for r in res['pair_cosines']:
 if r['relation_id'] in ['pair_g02_g06','pair_g01_g07','pair_g04_g10']:print(r)
