#!/usr/bin/env python3
"""Single offline page: three method introductions, each with shot1/shot3 3D views."""
import argparse
import html
import itertools
import json
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from build_three_method_static_scenes import DEFAULT_OUT, METHODS, load, save
from run_isolated_shot_static_3d import owned_compute_job

EDGES=[(i,j) for i,j in itertools.combinations(range(8),2) if (i^j) in (1,2,4)]
DESCRIPTIONS={
 'codex':('方法一 · Codex 直接估计三维场景',
   'Codex 根据同一 shot 的六张图、实体和二维框，估计桌面参考系、针孔相机以及物体中心、尺寸、旋转和误差范围。原始结果有些用一个状态覆盖多帧；这里按帧展开为 Gs，再使用误差范围导出的可靠度、逐帧重投影和可见范围加权融合。共享状态只作为同一个几何来源，不能算成六次独立预测。',
   '优势：能表达任意三维朝向，并利用场景语义建立桌面坐标。限制：尺度以桌长为单位，位置、尺寸和误差范围均为未标定的视觉估计；共享状态不提供独立的多帧几何验证。'),
 'boxer_codex_camera':('方法二 · Codex 相机参数 + BoxerNet',
   '沿用方法一估计的每帧相机内参和朝向，BoxerNet 接收单帧 RGB、冻结二维框和相机参数，逐帧预测三维框及模型分数，不输入深度。各帧 Gs 在该方法的局部坐标系内按模型分数、重投影和可见范围加权融合。相机平移使用原前端的零原点约定，不混入方法一的桌面原点。',
   '优势：几何框由专门模型逐帧预测，可与方法一比较框生成器的差别。限制：仍依赖 Codex 相机假设与单目尺度先验；Boxer 为重力对齐的7自由度框，不能精确表达任意倾斜、薄物体和关节形状。'),
 'boxer_geocalib':('方法三 · GeoCalib + BoxerNet',
   'GeoCalib 从同一 shot 的六张图估计共享内参，按固定相机假设汇总重力方向。BoxerNet 使用这组参数及每帧 RGB、二维框预测三维框，不输入深度。采用与方法二相同的质量加权与稳健融合规则，因此二、三行主要比较相机估计来源。',
   '优势：用专门标定模型提供焦距和重力方向。限制：仍无实测深度和真实尺度，固定相机假设及标定误差会影响整体布局；投影吻合度高不等于三维准确。')}


def camera_lines(camera,length):
    p=np.array(camera['position_world']);r=np.array(camera['R_world_from_camera']);k=np.array(camera['K']);w,h=camera['image_size']
    rays=np.array([[0,0,1],[w,0,1],[w,h,1],[0,h,1]])@np.linalg.inv(k).T
    tips=p+(rays*length)@r.T
    return dict(position=p.tolist(),forward_tip=(p+r[:,2]*length*1.6).tolist(),
                up_tip=(p-r[:,1]*length*.65).tolist(),frustum_corners=tips.tolist())


def polyline(segments):
    pts=[]
    for a,b in segments:pts += [list(a),list(b),[None,None,None]]
    return list(zip(*pts))


def figure(graph):
    valid=[e for e in graph['entities'] if e['geometry']]
    cloud=np.array([p for e in valid for p in e['geometry']['corners_world']]+[c['position_world'] for c in graph['cameras']])
    lo=cloud.min(0);hi=cloud.max(0);center=(lo+hi)/2;span=max(float(np.max(hi-lo)),.1);half=span*.56
    fig=go.Figure()
    for e in valid:
        eid=e['entity_id'].split('/')[-1];number=int(eid[1:]);color=f'hsl({number*137.508%360:.1f},65%,48%)'
        b=e['geometry'];points=b['corners_world'];xs,ys,zs=polyline([(points[a],points[z]) for a,z in EDGES])
        xs=list(xs)+[b['center_world'][0]];ys=list(ys)+[b['center_world'][1]];zs=list(zs)+[b['center_world'][2]]
        info=html.escape(e['name'])+'<br>'+eid+' · '+('投影支持较弱' if e['reliability']=='limited' else '有投影支持的估计')
        info += '<br>中心 '+str([round(v,3) for v in b['center_world']])+'<br>尺寸 '+str([round(v,3) for v in b['size_xyz']])
        info += f'<br>融合后投影中位IoU {e["fused_projection_median_iou"]:.3f}<br>参与帧 '+str(e['aggregation']['selected_frame_ids'])
        info += '<br>独立几何来源数 '+str(e['aggregation']['distinct_geometry_sources'])
        fig.add_trace(go.Scatter3d(x=xs,y=ys,z=zs,mode='lines+text',text=['']*(len(xs)-1)+[eid],
            textfont=dict(size=10,color=color),name=eid,legendgroup=eid,
            line=dict(color=color,width=4,dash='dot' if e['reliability']=='limited' else 'solid'),
            hovertemplate=info+'<extra></extra>'))
    unique=[]
    for camera in graph['cameras']:
        same=next((c for c in unique if np.allclose(c['camera']['position_world'],camera['position_world']) and np.allclose(c['camera']['R_world_from_camera'],camera['R_world_from_camera']) and np.allclose(c['camera']['K'],camera['K'])),None)
        if same:same['frame_ids'].append(camera['frame_id'])
        else:unique.append(dict(camera=camera,frame_ids=[camera['frame_id']]))
    camera_geometry=[]
    for index,entry in enumerate(unique):
        camera=entry['camera'];cg=camera_lines(camera,span*.12);camera_geometry.append(dict(frame_ids=entry['frame_ids'],**cg))
        p=cg['position'];corners=cg['frustum_corners'];name='相机 '+','.join(map(str,entry['frame_ids']))
        info=name+'<br>位置 '+str([round(v,4) for v in p])+'<br>朝向 '+str([round(v,4) for v in camera['forward_world']])+'<br>上方向 '+str([round(v,4) for v in camera['up_world']])
        xs,ys,zs=polyline([(p,q) for q in corners]+[(corners[i],corners[(i+1)%4]) for i in range(4)])
        fig.add_trace(go.Scatter3d(x=xs,y=ys,z=zs,mode='lines',line=dict(color='#cf6d10',width=3),name='相机视锥',legendgroup='camera',showlegend=index==0,hovertemplate=info+'<extra></extra>'))
        fig.add_trace(go.Scatter3d(x=[p[0]],y=[p[1]],z=[p[2]],mode='markers+text',marker=dict(size=5,color='#111827',symbol='diamond'),text=['Camera'],textposition='top center',legendgroup='camera',showlegend=False,hovertemplate=info+'<extra></extra>'))
        for tip,color,label in [(cg['forward_tip'],'#009da9','相机朝向'),(cg['up_tip'],'#539321','相机上方')]:
            fig.add_trace(go.Scatter3d(x=[p[0],tip[0]],y=[p[1],tip[1]],z=[p[2],tip[2]],mode='lines+markers',marker=dict(size=[0,3]),line=dict(color=color,width=6),name=label,showlegend=index==0,legendgroup='camera',hovertemplate=info+'<extra></extra>'))
            delta=np.array(tip)-p
            fig.add_trace(go.Cone(x=[tip[0]],y=[tip[1]],z=[tip[2]],u=[delta[0]],v=[delta[1]],w=[delta[2]],sizemode='absolute',sizeref=span*.035,anchor='tip',showscale=False,colorscale=[[0,color],[1,color]],showlegend=False,legendgroup='camera',hoverinfo='skip'))
    # Native axes remain visible; values are not implicitly aligned between methods.
    axis_length=span*.16
    for i,(color,label) in enumerate([('#d43e43','X'),('#38924e','Y'),('#3f70db','Z')]):
        end=np.zeros(3);end[i]=axis_length
        fig.add_trace(go.Scatter3d(x=[0,end[0]],y=[0,end[1]],z=[0,end[2]],mode='lines+text',text=['',label],line=dict(color=color,width=4),showlegend=False,hoverinfo='skip'))
    eye=np.array(graph['cameras'][0]['position_world'])-center+np.array([0,0,span*.65]);eye=eye/max(np.linalg.norm(eye),1e-9)*2.1
    scene=dict(aspectmode='cube',camera=dict(eye=dict(zip('xyz',eye)),up=dict(x=0,y=0,z=1)),
        **{axis+'axis':dict(title=axis.upper(),range=[float(center[i]-half),float(center[i]+half)],backgroundcolor='#f5f7fb',gridcolor='#dfe5ec',showbackground=True) for i,axis in enumerate('xyz')})
    fig.update_layout(height=610,margin=dict(l=0,r=0,t=10,b=90),paper_bgcolor='white',scene=scene,
        legend=dict(orientation='h',y=-.03,x=0,font=dict(size=10),groupclick='togglegroup'),uirevision=graph['method']+'/'+graph['shot_id'])
    return fig,camera_geometry


def render(root):
    owned_compute_job();sections=[];camera_records=[];first=True
    for method in METHODS:
        title,description,limits=DESCRIPTIONS[method];panels=[]
        for sid in ('shot1','shot3'):
            g=load(root/method/sid/'Gs_global.json');fig,camera=figure(g)
            camera_records.append(dict(method=method,shot_id=sid,cameras=camera))
            chart=pio.to_html(fig,full_html=False,include_plotlyjs=True if first else False,
                div_id=method+'_'+sid,config=dict(responsive=True,displaylogo=False,toImageButtonOptions=dict(format='png',scale=2)))
            first=False;c=g['counts'];metrics=f'{c["static_entities"]} 个静止实体 · {c["geometry_boxes"]} 个可绘制框 · {c.get("limited",0)} 个投影支持较弱'
            details=[]
            for e in g['entities']:
                details.append('<tr><td>'+html.escape(e['entity_id'].split('/')[-1]+' '+e['name'])+'</td><td>'+e['reliability']+'</td><td>'+str(e['aggregation'].get('selected_frame_ids',[]))+'</td><td>'+f'{e["fused_projection_median_iou"]:.3f}'+'</td></tr>')
            table='<details><summary>实体与参与帧明细</summary><table><tr><th>实体</th><th>支持状态</th><th>参与帧</th><th>融合投影IoU</th></tr>'+''.join(details)+'</table></details>'
            panels.append(f'<article><h3>{sid}</h3><p class="metrics">{metrics}</p>{chart}<p class="coord">坐标：{html.escape(g["coordinate_system"]["origin"])}；{html.escape(g["coordinate_system"]["scale"])}</p>{table}<p><a href="{method}/{sid}/Gs_global.json">Gs_global JSON</a> · <a href="{method}/{sid}/Gs_frames.json">逐帧 Gs / 权重与取舍</a></p></article>')
        sections.append(f'<section><h2>{title}</h2><p>{description}</p><p class="limits">{limits}</p><div class="pair">'+''.join(panels)+'</div></section>')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>三种方法 · Shot-level Gs_global</title>
<style>*{box-sizing:border-box}body{margin:0;background:#eef2f6;color:#172335;font:15px/1.65 system-ui,-apple-system,sans-serif}header{padding:28px 28px 20px;background:#12253b;color:#f4f7fc}h1{margin:0 0 12px;font-size:26px}header p{max-width:1450px;margin:8px 0;color:#d7e2ef}main{padding:18px;min-width:900px}section{margin:0 0 26px;padding:22px;border:1px solid #d9e0e8;border-radius:14px;background:white}h2{font-size:21px;margin:0 0 8px}h3{margin:10px 0 0;font-size:19px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}article{min-width:0;border:1px solid #dce3ec;border-radius:9px;padding:12px}.metrics,.coord{font-size:12px;color:#52657b;margin:3px 0}.limits{font-size:13px;color:#50647a;background:#f4f7fb;padding:10px 14px;border-left:3px solid #7c97b6}details{font-size:12px}summary{cursor:pointer;color:#245c8f}table{width:100%;border-collapse:collapse}td,th{padding:5px;border-bottom:1px solid #e2e8ef;text-align:left;overflow-wrap:anywhere}a{color:#245c8f}article>p:last-child{font-size:12px}</style></head><body><header>
<h1>G = Gm + Gs：三种方法的 Gs_global</h1>
<p>固定同一份逐 shot 独立静动划分：Shot1 17 个静止实体，Shot3 21 个。每行是一种几何生成方法；左为 Shot1，右为 Shot3。每幅图只显示一个整个 shot 的静态融合结果。</p>
<p>拖动旋转，滚轮缩放，点击图例隐藏实体；悬停查看位置、尺寸和来源。橙色视锥＋黑色菱形标出相机位置，青色箭头是相机朝向，绿色箭头是相机上方向。同位相机合并标注帧号。</p>
<p>融合权重 = 投影 IoU × 可见面积比的平方根 × 边界裁切系数 × 方法内可靠度因子。剔除不可见、无效、无投影重叠及明显中心离群帧；共享几何状态不重复计票。对中心、尺寸取加权中位数，对等价框朝向对齐后作合法旋转融合。</p>
<p>虚线表示投影支持较弱，保留展示以免隐藏方法失败；实线也只是有支持的估计。权重和“支持状态”不是校准置信度。两 shot、不同方法的坐标原点与尺度各自独立；颜色只在同一 shot 的三种方法间对应实体，不表示跨 shot 身份。没有跨 shot 配准或三维真值。</p>
</header><main>'''+''.join(sections)+'</main></body></html>'
    (root/'comparison.html').write_text(page)
    save(root/'camera_visualization.json',camera_records)
    print(str(root/'comparison.html'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,default=DEFAULT_OUT)
    render(p.parse_args().run)
