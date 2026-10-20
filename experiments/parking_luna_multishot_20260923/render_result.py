#!/usr/bin/env python3
import json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

R=Path(__file__).resolve().parent/'shared/parking4'
OUT=Path(__file__).resolve().parent
colors={'Shot1':'#2563eb','Shot2':'#f97316','Shot3':'#16a34a','Shot4':'#9333ea'}
for sid in ['Shot1','Shot2','Shot3','Shot4']:
    g=json.loads((R/'selected'/f'{sid}_scene.json').read_text())
    fig,ax=plt.subplots(figsize=(6,6),dpi=180)
    for e in g['entities']:
        geom=e.get('geometry')
        if not geom: continue
        cs=geom['corners_world']; pts=[(p[0],p[1]) for p in cs]
        # bottom/top corner ordering from Boxer; convex hull via angle around center
        cx,cy=geom['center_world'][:2]
        hull=sorted(set(pts),key=lambda p:__import__('math').atan2(p[1]-cy,p[0]-cx))
        ax.add_patch(Polygon(hull,closed=True,fill=False,edgecolor=colors[sid],linewidth=1.4,alpha=.8))
        ax.scatter(cx,cy,c=colors[sid],s=16)
        ax.text(cx,cy,e['name'],fontsize=7,color='#111827')
    ax.set_aspect('equal');ax.grid(alpha=.25);ax.set_xlabel('native x');ax.set_ylabel('native y')
    ax.set_title(f'{sid}: native Pi3X scene coordinates')
    fig.tight_layout();fig.savefig(OUT/f'{sid}_native_topview.png',bbox_inches='tight');plt.close(fig)
fig,axes=plt.subplots(2,2,figsize=(10,10),dpi=180)
for ax,sid in zip(axes.flat,['Shot1','Shot2','Shot3','Shot4']):
    g=json.loads((R/'selected'/f'{sid}_scene.json').read_text())
    for e in g['entities']:
        geom=e.get('geometry')
        if not geom:continue
        cs=geom['corners_world'];cx,cy=geom['center_world'][:2]
        hull=sorted(set((p[0],p[1]) for p in cs),key=lambda p:__import__('math').atan2(p[1]-cy,p[0]-cx))
        ax.add_patch(Polygon(hull,closed=True,fill=False,edgecolor=colors[sid],linewidth=1.2,alpha=.8));ax.scatter(cx,cy,c=colors[sid],s=11);ax.text(cx,cy,e['name'],fontsize=6)
    ax.set_aspect('equal');ax.grid(alpha=.25);ax.set_title(f'{sid} (separate native frame)',color=colors[sid],fontweight='bold');ax.set_xlabel('x');ax.set_ylabel('y')
fig.suptitle('Parking case: no accepted inter-shot transform; panels must not be overlaid',fontsize=13,fontweight='bold')
fig.tight_layout();fig.savefig(OUT/'native_topviews_unaligned.png',bbox_inches='tight');plt.close(fig)
