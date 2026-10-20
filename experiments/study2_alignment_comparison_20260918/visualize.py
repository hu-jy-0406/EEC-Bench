"""Render frozen full-run alignments; no inference or fitting."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/eec_alignment_mpl')
import json, hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.spatial import ConvexHull
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
SOURCES=[('original','Original full pipeline','study2_full_fresh_20260918'),('joint','Anchor-first + joint review','study2_anchor_joint_fresh_20260918')]
COLORS=['#1874c5','#e47820']
EDGES=[(i,j) for i in range(8) for j in range(i+1,8) if (i^j).bit_count()==1]
read=lambda p:json.loads(p.read_text())
records=[]; provenance={}
for key,title,dirname in SOURCES:
    folder=ROOT/dirname/'study2'
    rp=folder/'registration/roma_geometry/registration.json'
    fit=read(rp)['fits']['all_structures']
    R=np.array(fit['rotation']);t=np.array(fit['translation']);s=fit['scale']
    assert np.allclose(R.T@R,np.eye(3)) and s>0
    rows=[]
    for side,shot in enumerate(['shot1','shot3']):
        p=folder/'selected'/f'{shot}_static_scene.json'
        provenance[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        scene=read(p)
        assert scene['coordinate_system']['z_axis']=='up'
        for e in scene['entities']:
            assert e['motion_status']=='static'
            g=e['geometry'];v=np.array(g['corners_world']);c=np.array(g['center_world'])
            if side: v=s*v@R.T+t;c=s*c@R.T+t
            assert np.allclose(v.mean(0),c)
            labels={'shot1/e2':'Mug','shot1/e5':'Desk','shot1/e7':'Pencil cup','shot1/e14':'Radiator','shot3/e2':'Mug','shot3/e7':'Desk','shot3/e9':'Pencil cup','shot3/e18':'Radiator'}
            label=labels.get(e['entity_id'])
            rows.append(dict(side=side,id=e['entity_id'],name=e['name'],corners=v.tolist(),center=c.tolist(),label=label))
    provenance[str(rp)]=hashlib.sha256(rp.read_bytes()).hexdigest()
    records.append(dict(key=key,title=title,fit=fit,rows=rows))
points=np.concatenate([np.array(e['corners']) for r in records for e in r['rows']])
lo=points.min(0);hi=points.max(0);pad=(hi-lo)*.075;lo-=pad;hi+=pad
handles=[Line2D([0],[0],color=c,lw=2,label=l) for c,l in zip(COLORS,['Shot1 (fixed)','Shot3 (transformed)'])]
for r in records:
    fig=plt.figure(figsize=(14,7.5),facecolor='white')
    ax=fig.add_subplot(121,projection='3d');top=fig.add_subplot(122)
    for e in r['rows']:
        v=np.array(e['corners']);c=np.array(e['center']);color=COLORS[e['side']];major=e['label'] is not None
        for i,j in EDGES:ax.plot(*v[[i,j]].T,color=color,lw=1.25 if major else .65,alpha=.85 if major else .32)
        hull=ConvexHull(v[:,:2]);poly=v[np.r_[hull.vertices,hull.vertices[0]],:2]
        top.plot(*poly.T,color=color,lw=1.5 if major else .8,alpha=.95 if major else .42)
        top.scatter(*c[:2],s=14 if major else 5,c=color,alpha=.9)
        if major:
            label=('S1 ' if e['side']==0 else 'S3 ')+e['label']
            ax.text(*c,label,color=color,fontsize=8)
            top.annotate(label,c[:2],xytext=(8,12 if e['side']==0 else -15),textcoords='offset points',fontsize=9,color=color,arrowprops=dict(arrowstyle='-',color=color,lw=.6),bbox=dict(facecolor='white',alpha=.8,edgecolor='none',pad=1))
    ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),zlim=(lo[2],hi[2]),xlabel='X',ylabel='Y',zlabel='Z (up)',title='All static 3D boxes')
    ax.set_box_aspect(hi-lo);ax.view_init(elev=24,azim=-62);ax.set_proj_type('ortho')
    top.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),xlabel='X',ylabel='Y',title='Top view (XY)');top.set_aspect('equal');top.grid(alpha=.15)
    n=[sum(e['side']==i for e in r['rows']) for i in (0,1)]
    fig.suptitle(f"{r['title']}  |  Study2 Shot1 + Shot3\nYaw {r['fit']['yaw_deg']:.2f} deg; scale {r['fit']['scale']:.4f}; static boxes {n[0]} + {n[1]}",fontsize=15,y=.99)
    fig.legend(handles=handles,loc='lower center',ncol=2,bbox_to_anchor=(.5,.043),frameon=False)
    fig.text(.5,.018,'Coordinates: each run\'s fixed Shot1 scene; model units, not calibrated meters. Same view and axis limits. All static entities shown; overlap does not assert identity.',ha='center',fontsize=8,color='#555555')
    fig.tight_layout(rect=[0,.08,1,.91]);fig.savefig(OUT/f"{r['key']}.png",dpi=140);plt.close(fig)
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig=make_subplots(rows=1,cols=2,specs=[[{'type':'scene'},{'type':'scene'}]],subplot_titles=[r['title'] for r in records])
    for col,r in enumerate(records,1):
        for e in r['rows']:
            v=np.array(e['corners']);c=np.array(e['center']);xyz=[[],[],[]]
            for i,j in EDGES:
                for k in range(3):xyz[k].extend([v[i,k],v[j,k],None])
            shot='Shot1' if e['side']==0 else 'Shot3';color=COLORS[e['side']]
            fig.add_trace(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',line=dict(color=color,width=3),opacity=.6,name=e['id']+' '+e['name'],showlegend=False,hoverinfo='name'),row=1,col=col)
            fig.add_trace(go.Scatter3d(x=[c[0]],y=[c[1]],z=[c[2]],mode='markers',marker=dict(color=color,size=3),name=e['id']+' '+e['name'],hovertemplate='%{fullData.name}<br>X=%{x:.3f}, Y=%{y:.3f}, Z=%{z:.3f}<extra></extra>',legendgroup=shot,showlegend=False),row=1,col=col)
    scene=dict(xaxis=dict(range=[lo[0],hi[0]],title='X'),yaxis=dict(range=[lo[1],hi[1]],title='Y'),zaxis=dict(range=[lo[2],hi[2]],title='Z (up)'),aspectmode='data',camera=dict(eye=dict(x=1.5,y=-2,z=1.2),up=dict(x=0,y=0,z=1)))
    fig.update_layout(scene=scene,scene2=scene,height=850,title='Study2 frozen alignment comparison | Blue: Shot1; Orange: transformed Shot3',margin=dict(l=0,r=0,b=20,t=90))
    fig.write_html(str(OUT/'interactive.html'),include_plotlyjs=True)
except ImportError:
    pass
(OUT/'aligned_boxes.json').write_text(json.dumps(records,indent=2))
(OUT/'manifest.json').write_text(json.dumps(dict(sources=provenance,shared_limits=[lo.tolist(),hi.tolist()],method='Stored all_structures transform applied to all static fused boxes; no re-fit',counts={r['key']:len(r['rows']) for r in records}),indent=2))
for p,h in provenance.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
print(json.dumps({'outputs':[p.name for p in OUT.iterdir()],'counts':{r['key']:len(r['rows']) for r in records}}))
